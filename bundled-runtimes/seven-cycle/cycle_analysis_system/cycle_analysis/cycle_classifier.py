"""
周期分类器

实现周期阶段分类、状态判断和趋势预测功能。
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from loguru import logger

from ..config.cycles_config import cycles_config, CycleType, CyclePhase
from .cycle_detector import CycleDetector
from .cycle_filter import CycleFilter


class CycleClassifier:
    """周期分类器类"""
    
    def __init__(self):
        self.cycles_config = cycles_config
        self.detector = CycleDetector()
        self.filter = CycleFilter()
        self.scaler = StandardScaler()
        self.classifier = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            max_depth=10
        )
        
    def classify_cycle_phase(
        self,
        position: float,
        amplitude: float = 1.0,
        trend: float = 0.0
    ) -> CyclePhase:
        """
        分类周期阶段
        
        Args:
            position: 周期位置 (0-1)
            amplitude: 周期振幅
            trend: 趋势方向
            
        Returns:
            CyclePhase: 周期阶段
        """
        try:
            # 基础位置分类
            base_phase = self.cycles_config.classify_cycle_phase(position)
            
            # 考虑振幅和趋势的修正
            if amplitude < 0.5:  # 低振幅时，阶段可能不明显
                logger.warning(f"周期振幅较低 ({amplitude:.3f})，阶段判断可能不准确")
            
            # 根据趋势微调阶段判断
            if trend > 0.1:  # 强上升趋势
                if base_phase == CyclePhase.CONTRACTION_LATE:
                    return CyclePhase.EXPANSION_EARLY
                elif base_phase == CyclePhase.CONTRACTION_EARLY:
                    return CyclePhase.EXPANSION_EARLY
            elif trend < -0.1:  # 强下降趋势
                if base_phase == CyclePhase.EXPANSION_LATE:
                    return CyclePhase.CONTRACTION_EARLY
                elif base_phase == CyclePhase.EXPANSION_EARLY:
                    return CyclePhase.CONTRACTION_EARLY
            
            return base_phase
            
        except Exception as e:
            logger.error(f"周期阶段分类失败: {str(e)}")
            return CyclePhase.EXPANSION_EARLY
    
    def create_cycle_features(
        self,
        data: pd.Series,
        window: int = 12
    ) -> pd.DataFrame:
        """
        创建周期特征
        
        Args:
            data: 时间序列数据
            window: 特征计算窗口
            
        Returns:
            pd.DataFrame: 特征数据
        """
        try:
            features = pd.DataFrame(index=data.index)
            
            # 基础统计特征
            features['value'] = data
            features['ma_short'] = data.rolling(window=window//2).mean()
            features['ma_long'] = data.rolling(window=window).mean()
            features['std'] = data.rolling(window=window).std()
            features['skew'] = data.rolling(window=window).skew()
            features['kurt'] = data.rolling(window=window).kurt()
            
            # 趋势特征
            features['trend'] = data.diff()
            features['trend_ma'] = features['trend'].rolling(window=window//2).mean()
            features['momentum'] = data.pct_change(periods=window//2)
            
            # 相对位置特征
            rolling_min = data.rolling(window=window).min()
            rolling_max = data.rolling(window=window).max()
            features['relative_position'] = (data - rolling_min) / (rolling_max - rolling_min + 1e-8)
            
            # 周期成分特征
            for cycle_type in CycleType:
                try:
                    cycle_component = self.filter.extract_cycle_component(data, cycle_type)
                    if not cycle_component.empty:
                        cycle_config = self.cycles_config.get_cycle(cycle_type)
                        col_name = f"cycle_{cycle_config.name}"
                        
                        # 对齐索引
                        aligned_component = cycle_component.reindex(data.index, method='nearest')
                        features[col_name] = aligned_component
                        
                        # 周期相位
                        phase_data = self.filter.calculate_cycle_phase(cycle_component)
                        if not phase_data.empty:
                            aligned_phase = phase_data.reindex(data.index, method='nearest')
                            features[f"{col_name}_phase"] = aligned_phase
                        
                        # 周期振幅
                        amplitude = self.filter.calculate_cycle_amplitude(cycle_component)
                        features[f"{col_name}_amplitude"] = amplitude
                        
                except Exception as e:
                    logger.warning(f"提取{cycle_type.value}特征失败: {str(e)}")
            
            # 填充缺失值
            features = features.fillna(method='forward').fillna(method='backward')
            
            return features
            
        except Exception as e:
            logger.error(f"创建周期特征失败: {str(e)}")
            return pd.DataFrame()
    
    def generate_cycle_labels(
        self,
        data: pd.Series
    ) -> pd.Series:
        """
        生成周期标签
        
        Args:
            data: 时间序列数据
            
        Returns:
            pd.Series: 周期阶段标签
        """
        try:
            labels = pd.Series(index=data.index, dtype=str)
            
            # 获取所有周期状态
            cycle_status = self.detector.get_cycle_status(data)
            
            # 计算复合周期得分
            composite_score = self.detector.calculate_composite_cycle_score(data)
            
            # 根据复合得分确定主要阶段
            expansion_score = composite_score['expansion_score']
            contraction_score = composite_score['contraction_score']
            
            if expansion_score > contraction_score:
                if expansion_score > 0.6:
                    main_phase = "扩张期"
                else:
                    main_phase = "扩张转换期"
            else:
                if contraction_score > 0.6:
                    main_phase = "收缩期"
                else:
                    main_phase = "收缩转换期"
            
            # 为所有时间点分配标签
            labels[:] = main_phase
            
            return labels
            
        except Exception as e:
            logger.error(f"生成周期标签失败: {str(e)}")
            return pd.Series(index=data.index, dtype=str)
    
    def train_cycle_classifier(
        self,
        training_data: Dict[str, pd.Series],
        test_size: float = 0.2
    ) -> Dict[str, float]:
        """
        训练周期分类器
        
        Args:
            training_data: 训练数据字典
            test_size: 测试集比例
            
        Returns:
            Dict[str, float]: 训练结果
        """
        try:
            all_features = []
            all_labels = []
            
            # 为每个时间序列生成特征和标签
            for name, data in training_data.items():
                logger.info(f"处理训练数据: {name}")
                
                features = self.create_cycle_features(data)
                labels = self.generate_cycle_labels(data)
                
                if not features.empty and not labels.empty:
                    # 确保索引对齐
                    common_index = features.index.intersection(labels.index)
                    if len(common_index) > 0:
                        features_aligned = features.loc[common_index]
                        labels_aligned = labels.loc[common_index]
                        
                        all_features.append(features_aligned)
                        all_labels.extend(labels_aligned.tolist())
            
            if not all_features:
                raise ValueError("没有有效的训练数据")
            
            # 合并所有特征
            X = pd.concat(all_features, ignore_index=True)
            y = np.array(all_labels)
            
            # 处理缺失值
            X = X.fillna(0)
            
            # 标准化特征
            X_scaled = self.scaler.fit_transform(X)
            
            # 分割训练集和测试集
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=test_size, random_state=42, stratify=y
            )
            
            # 训练分类器
            self.classifier.fit(X_train, y_train)
            
            # 评估性能
            train_score = self.classifier.score(X_train, y_train)
            test_score = self.classifier.score(X_test, y_test)
            
            # 特征重要性
            feature_importance = dict(zip(X.columns, self.classifier.feature_importances_))
            
            logger.info(f"分类器训练完成 - 训练准确率: {train_score:.3f}, 测试准确率: {test_score:.3f}")
            
            return {
                'train_accuracy': train_score,
                'test_accuracy': test_score,
                'feature_count': len(X.columns),
                'sample_count': len(X),
                'feature_importance': feature_importance
            }
            
        except Exception as e:
            logger.error(f"训练周期分类器失败: {str(e)}")
            return {}
    
    def predict_cycle_phase(
        self,
        data: pd.Series,
        return_probability: bool = False
    ) -> Union[str, Dict[str, float]]:
        """
        预测周期阶段
        
        Args:
            data: 时间序列数据
            return_probability: 是否返回概率
            
        Returns:
            Union[str, Dict[str, float]]: 预测结果
        """
        try:
            # 创建特征
            features = self.create_cycle_features(data)
            
            if features.empty:
                return "未知" if not return_probability else {"未知": 1.0}
            
            # 使用最新的特征进行预测
            latest_features = features.iloc[-1:].fillna(0)
            
            # 标准化
            features_scaled = self.scaler.transform(latest_features)
            
            if return_probability:
                # 返回概率分布
                probabilities = self.classifier.predict_proba(features_scaled)[0]
                classes = self.classifier.classes_
                return dict(zip(classes, probabilities))
            else:
                # 返回预测类别
                prediction = self.classifier.predict(features_scaled)[0]
                return prediction
                
        except Exception as e:
            logger.error(f"预测周期阶段失败: {str(e)}")
            return "未知" if not return_probability else {"未知": 1.0}
    
    def analyze_cycle_transition(
        self,
        data: pd.Series,
        lookback_periods: int = 12
    ) -> Dict[str, Union[str, float, List]]:
        """
        分析周期转换
        
        Args:
            data: 时间序列数据
            lookback_periods: 回看期数
            
        Returns:
            Dict[str, Union[str, float, List]]: 转换分析结果
        """
        try:
            if len(data) < lookback_periods:
                return {'error': '数据不足'}
            
            # 获取历史周期状态
            recent_data = data.iloc[-lookback_periods:]
            historical_phases = []
            
            for i in range(len(recent_data)):
                subset_data = recent_data.iloc[:i+1]
                if len(subset_data) >= 3:  # 最少需要3个数据点
                    phase = self.predict_cycle_phase(subset_data)
                    historical_phases.append(phase)
            
            if not historical_phases:
                return {'error': '无法分析历史阶段'}
            
            # 检测阶段转换
            transitions = []
            for i in range(1, len(historical_phases)):
                if historical_phases[i] != historical_phases[i-1]:
                    transitions.append({
                        'from': historical_phases[i-1],
                        'to': historical_phases[i],
                        'period': i
                    })
            
            # 当前状态
            current_phase = historical_phases[-1]
            
            # 预测下一阶段概率
            next_phase_probs = self.predict_cycle_phase(data, return_probability=True)
            
            # 计算转换概率
            transition_probability = 0.0
            if len(historical_phases) >= 2:
                recent_changes = sum(1 for i in range(1, min(6, len(historical_phases))) 
                                   if historical_phases[-i] != historical_phases[-i-1])
                transition_probability = recent_changes / min(5, len(historical_phases)-1)
            
            return {
                'current_phase': current_phase,
                'historical_phases': historical_phases,
                'transitions': transitions,
                'transition_count': len(transitions),
                'transition_probability': transition_probability,
                'next_phase_probabilities': next_phase_probs,
                'stability_score': 1 - transition_probability
            }
            
        except Exception as e:
            logger.error(f"分析周期转换失败: {str(e)}")
            return {'error': str(e)}
    
    def get_cycle_classification_summary(
        self,
        data: pd.Series
    ) -> Dict[str, Dict]:
        """
        获取周期分类摘要
        
        Args:
            data: 时间序列数据
            
        Returns:
            Dict[str, Dict]: 分类摘要
        """
        try:
            summary = {}
            
            # 获取所有周期的状态
            cycle_status = self.detector.get_cycle_status(data)
            
            # 复合周期分析
            composite_score = self.detector.calculate_composite_cycle_score(data)
            
            # 转换分析
            transition_analysis = self.analyze_cycle_transition(data)
            
            # 整体预测
            overall_prediction = self.predict_cycle_phase(data, return_probability=True)
            
            summary['individual_cycles'] = cycle_status
            summary['composite_analysis'] = composite_score
            summary['transition_analysis'] = transition_analysis
            summary['overall_prediction'] = overall_prediction
            
            # 计算信心度
            confidence_scores = []
            for cycle_name, status in cycle_status.items():
                amplitude = status.get('amplitude', 0)
                weight = status.get('weight', 0)
                confidence = min(1.0, amplitude * weight * 2)  # 简单的信心度计算
                confidence_scores.append(confidence)
            
            summary['confidence_score'] = np.mean(confidence_scores) if confidence_scores else 0.0
            
            # 风险评估
            risk_factors = []
            if composite_score.get('cycle_strength', 0) < -0.5:
                risk_factors.append("强收缩信号")
            if transition_analysis.get('transition_probability', 0) > 0.7:
                risk_factors.append("高转换概率")
            if summary['confidence_score'] < 0.3:
                risk_factors.append("低信心度")
            
            summary['risk_factors'] = risk_factors
            summary['risk_level'] = len(risk_factors)
            
            return summary
            
        except Exception as e:
            logger.error(f"获取周期分类摘要失败: {str(e)}")
            return {'error': str(e)} 
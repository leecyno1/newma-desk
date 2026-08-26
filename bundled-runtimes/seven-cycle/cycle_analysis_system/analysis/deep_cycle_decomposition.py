import numpy as np
import pandas as pd
from scipy import signal
import statsmodels.api as sm
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
from sklearn.metrics import r2_score, mean_squared_error
import warnings

# 忽略警告
warnings.filterwarnings('ignore')

class CycleDecomposer:
    """
    周期分解器：使用带通滤波器 + HP滤波 将时间序列分解为 Trend + Cycles + Residual。
    """
    
    def __init__(self, periods=[200, 100, 42, 21, 12], sample_rate=1):
        """
        初始化分解器
        :param periods: 目标周期列表（单位：月）
        :param sample_rate: 采样频率（1=月频）
        """
        self.periods = np.array(periods)
        self.sample_rate = sample_rate
        self.filters = {}
        self._design_filters()
        
    def _design_filters(self):
        """
        设计Butterworth带通滤波器组
        """
        nyquist = 0.5 * self.sample_rate
        
        for p in self.periods:
            # 设定通带范围：中心频率的 +/- 25% (放宽以适应周期漂移)
            center_freq = 1.0 / p
            low_cut = 1.0 / (p * 1.33)  
            high_cut = 1.0 / (p * 0.8) 
            
            # 归一化频率
            low = low_cut / nyquist
            high = high_cut / nyquist
            
            # 边界保护
            if low <= 0: low = 0.001
            if high >= 1: high = 0.999
            
            # 设计2阶Butterworth滤波器 (filtfilt会使其变为4阶零相位)
            sos = signal.butter(2, [low, high], btype='band', output='sos')
            self.filters[p] = sos
            
    def decompose(self, series: pd.Series, lamb=14400) -> pd.DataFrame:
        """
        对序列进行分解
        :param series: 输入时间序列 (pandas Series)
        :param lamb: HP滤波参数，月频数据通常取 14400
        :return: DataFrame, 包含 Trend, Cycles, Residual, Phase info
        """
        # 1. 预处理：处理缺失值
        series = series.interpolate(method='linear').fillna(method='bfill').fillna(method='ffill')
        original_values = series.values
        
        # 2. 趋势分离：使用 HP 滤波 (Hodrick-Prescott Filter)
        # cycle_hp, trend_hp = sm.tsa.filters.hpfilter(series, lamb=lamb)
        # 注意：statsmodels 的 hpfilter 返回 (cycle, trend)
        # 我们将 hp_cycle 作为待进一步分解的波动项
        cycle_hp, trend_hp = sm.tsa.filters.hpfilter(original_values, lamb=lamb)
        
        results = {}
        reconstructed_cycles = np.zeros_like(original_values)
        
        # 3. 逐个周期滤波 (对 HP Cycle 进行分解)
        for p in self.periods:
            sos = self.filters[p]
            # 使用 filtfilt 进行零相位滤波
            try:
                # 对去趋势后的序列进行带通滤波
                component = signal.sosfiltfilt(sos, cycle_hp)
            except Exception as e:
                component = np.zeros_like(cycle_hp)
            
            results[f'Cycle_{p}m'] = component
            
            # 计算瞬时相位 (Hilbert Transform)
            analytic_signal = signal.hilbert(component)
            phase = np.angle(analytic_signal) # 弧度 [-pi, pi]
            results[f'Phase_{p}m'] = phase
            
            reconstructed_cycles += component
            
        # 4. 计算残差
        # Residual = (Original - Trend) - Sum(Cycles)
        #          = HP_Cycle - Sum(Cycles)
        residual = cycle_hp - reconstructed_cycles
        
        # 5. 组装结果
        df_res = pd.DataFrame(results, index=series.index)
        df_res['Trend'] = trend_hp
        df_res['Residual'] = residual
        df_res['Original'] = original_values
        
        # 校验列：重构值
        df_res['Reconstructed'] = df_res['Trend'] + reconstructed_cycles + df_res['Residual']
        
        return df_res

class DeepCyclePredictor:
    """
    深度周期预测器：使用MLP（多层感知机）拟合周期分量的非线性叠加关系。
    """
    
    def __init__(self, lookback=12, forecast_horizon=1):
        """
        :param lookback: 回看窗口长度（月）
        :param forecast_horizon: 预测未来步数（月）
        """
        self.lookback = lookback
        self.horizon = forecast_horizon
        # 使用 MLPRegressor 模拟深度学习网络
        # 隐藏层结构：(64, 32)
        self.model = MLPRegressor(
            hidden_layer_sizes=(64, 32),
            activation='relu',
            solver='adam',
            max_iter=1000,
            random_state=42,
            early_stopping=True
        )
        self.scaler = StandardScaler()
        
    def prepare_features(self, decomposed_df: pd.DataFrame, target_col='Original'):
        """
        构建特征工程：使用过去N个月的各周期分量作为特征
        """
        # 特征列：所有周期分量 + 趋势 + 残差
        feature_cols = [c for c in decomposed_df.columns if c != 'Original']
        data = decomposed_df[feature_cols].values
        target = decomposed_df[target_col].values
        
        X, y = [], []
        
        # 构建滑动窗口样本
        for i in range(self.lookback, len(data) - self.horizon + 1):
            # 特征：过去 lookback 个月的所有分量数据 flattened
            # 形状: [lookback * num_components]
            feature_window = data[i-self.lookback:i].flatten()
            X.append(feature_window)
            
            # 目标：未来第 horizon 个月的值
            y.append(target[i + self.horizon - 1])
            
        return np.array(X), np.array(y)
    
    def train(self, X, y):
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        print(f"Model trained. Score: {self.model.score(X_scaled, y):.4f}")
        
    def predict(self, X):
        X_scaled = self.scaler.transform(X)
        return self.model.predict(X_scaled)

def run_demo_analysis():
    """
    运行演示分析
    """
    print("=== 开始周期分解与预测演示 ===")
    
    # 1. 生成模拟数据 (模拟 1984-2024, 480个月)
    dates = pd.date_range(start='1984-01-01', periods=480, freq='M')
    t = np.arange(480)
    
    # 构造合成信号：趋势 + 5个周期 + 噪音
    # 周期：200, 100, 42, 21, 12
    trend = 0.05 * t  # 长期向上趋势
    c200 = 2.0 * np.sin(2 * np.pi * t / 200)
    c100 = 1.5 * np.sin(2 * np.pi * t / 100 + 1)
    c42  = 1.0 * np.sin(2 * np.pi * t / 42 + 2)
    c21  = 0.8 * np.sin(2 * np.pi * t / 21 + 0.5)
    c12  = 0.5 * np.sin(2 * np.pi * t / 12)
    noise = np.random.normal(0, 0.3, 480)
    
    y = trend + c200 + c100 + c42 + c21 + c12 + noise
    series = pd.Series(y, index=dates, name='Simulated_GDP_YoY')
    
    print(f"生成模拟数据: {len(series)} 个月")
    
    # 2. 周期分解
    decomposer = CycleDecomposer(periods=[200, 100, 42, 21, 12])
    df_decomp = decomposer.decompose(series)
    
    print("\n分解完成。前5行数据：")
    print(df_decomp.head())
    
    # 3. 深度学习预测
    predictor = DeepCyclePredictor(lookback=24, forecast_horizon=1)
    
    # 划分训练集和测试集 (前80%训练，后20%测试)
    split_idx = int(len(df_decomp) * 0.8)
    train_df = df_decomp.iloc[:split_idx]
    test_df = df_decomp.iloc[split_idx:]
    
    print(f"\n训练集大小: {len(train_df)}, 测试集大小: {len(test_df)}")
    
    # 准备数据
    X_train, y_train = predictor.prepare_features(train_df)
    X_test, y_test = predictor.prepare_features(test_df) # 注意：这里测试集构建其实需要用到训练集末尾的数据作为lookback，简化处理暂略
    
    # 训练
    predictor.train(X_train, y_train)
    
    # 预测
    y_pred = predictor.predict(X_test)
    
    # 评估
    r2 = r2_score(y_test, y_pred)
    mse = mean_squared_error(y_test, y_pred)
    print(f"\n测试集评估:\nR2 Score: {r2:.4f}\nMSE: {mse:.4f}")
    
    # 4. 结果展示 (简单打印)
    print("\n解耦分析示例 (最后5个月):")
    last_5 = df_decomp.iloc[-5:]
    for idx, row in last_5.iterrows():
        print(f"Date: {idx.strftime('%Y-%m')}")
        print(f"  实际值: {row['Original']:.2f}")
        print(f"  = 趋势({row['Trend']:.2f}) + 200m({row['Cycle_200m']:.2f}) + 100m({row['Cycle_100m']:.2f}) + ...")
        
if __name__ == "__main__":
    run_demo_analysis()

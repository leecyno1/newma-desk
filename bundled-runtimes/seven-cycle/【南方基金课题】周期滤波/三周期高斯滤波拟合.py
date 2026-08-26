# -*- coding: utf-8 -*-
"""
Created on Fri Feb  2 15:42:36 2024

@author: Ying Zongxun
"""
import numpy as np
import pandas as pd
import tqdm
from scipy.signal import detrend
import statsmodels.api as sm

## 高斯滤波函数
def gauss_wave_predict_py(wave,period,n_fft,n_predict,gauss_alpha):
    ### 输入
    # wave：       输入序列，为列向量
    # period：     需要提取的周期长度，单位为月
    # n_fft：      FFT长度，也即填0后的长度
    # n_predict：  外延预测的长度
    # gauss_alpha：高斯滤波器带宽
    ### 输出
    # output：滤波提取的目标周期成分，长度为输入长度+n_predict
    ###
    # 1.填充0
    wave_pad = np.pad(wave, (n_fft-len(wave), 0), 'constant', constant_values=0)
    # 2.进行fft变换
    wave_fft = np.fft.fft(wave_pad,n=n_fft)
    # 3.进行高斯滤波频率响应，注意这里只刻画了低频部分，后续做共轭对称处理
    gauss_index = np.arange(1, n_fft+1)
    center_frequency = n_fft/period+1
    gauss_win = np.exp(-((gauss_index-center_frequency)**2)/(gauss_alpha**2))
    
    # 4.频域滤波，因为时域为实数，所以频域序列有共轭对称的属性
    wave_filter = wave_fft*gauss_win
    if n_fft%2 == 0:
        wave_filter[int(n_fft/2+2)-1:n_fft] = np.conj(wave_filter[int(n_fft/2)-1:0:-1])
    else:
        wave_filter[int((n_fft-1)/2+2)-1:n_fft] = np.conj(wave_filter[int((n_fft-1)/2):0:-1])
    # 5.逆傅里叶变换得到时域还原序列，外延预测本质上是在延拓主值序列
    ret = np.real(np.fft.ifft(wave_filter))
    output = np.concatenate((ret[-len(wave):], ret[:n_predict]))
    return output

#######################################################################
## 下面开始对序列做高斯滤波，提取目标周期，并对原始序列做回归
## 注意：默认输入的资产序列是时间对齐的且均为有效数据
#######################################################################

## 设置参数
## 文件名和标签名，如果只有一个标签，指定参数为0即可
file_name_now = 'data'
sheet_name_now = 0
# 预处理，none-不作处理，zero-零均值，detrend-去趋势，YoY-对数同比
# 对于股票指数类数据，自身包含趋势项，采用对数同比处理
# 对于宏观指标数据，因为已经是同比数据，可进行零均值或去趋势项处理
method_now = 'YoY'

# 高斯滤波目标周期，可以任意设置周期个数
periods = np.array([42,100,200])
len_per = np.size(periods,0)

# 预测长度，单位为月
predict_len = 12

# FFT长度
fft_size = 4096

# 高斯滤波带宽
gauss_alpha = 10

# 文件保存名
periods_str_list = [f'{x:g}' for x in periods]
periods_joined = '-'.join(periods_str_list)
save_file_name = file_name_now+'-'+periods_joined+'v0.xlsx'

## 读取数据
# 读取数据文件
read_file = file_name_now+'.xlsx'
df_data = pd.read_excel(read_file,sheet_name=sheet_name_now,index_col=0)
dates = df_data.index
asset_name = df_data.columns

########################################################################
## 遍历每个资产，进行高斯滤波，并将结果写入文件
asset_num = np.size(df_data,1)
row = 1+len(periods) # 单变量回归+汇总回归
col = 3+len(periods) # 截距+回归系数+R2+P值
out_regress_value = np.zeros([row*asset_num,col])
out_regress_col_name = np.full((col,),'',dtype=np.object_)
out_regress_col_name[0:2] = ['品种','Intercept']
for i_name in range(col-4):
    out_regress_col_name[i_name+2] = 'Beta'+str(i_name-3+1)
out_regress_col_name[-2:] = ['R2','P-Value']

out_regress_index_name = np.full((row*asset_num,),'',dtype=np.object_)

# 设置wxcel文件句柄
writer = pd.ExcelWriter(save_file_name)

# 对每个资产开始处理
for iAsset in tqdm.trange(asset_num):
    # step1: 对数据进行预处理
    seq_ori = df_data.iloc[:,iAsset].copy().values
    valid_index = ~np.isnan(seq_ori)
    seq = seq_ori[valid_index]
    # 生成日期
    seq_dates = dates[valid_index]
    new_dates = pd.date_range(start=seq_dates[-1] + pd.offsets.MonthEnd(1), periods=predict_len, freq='M')
    all_dates = seq_dates.append(new_dates)
    seq_len = int(len(seq))
    if method_now == 'YoY':
        log_seq = np.log(seq[12:])-np.log(seq[:-12])
        skip_len = 12
        method_name = '同比处理'
    elif method_now == 'zero':
        log_seq = seq-np.mean(seq)
        skip_len = 0
        method_name = '零均值'
    elif method_now == 'detrend':
        log_seq = detrend(seq, type='linear')
        skip_len = 0
        method_name = '去趋势'
    else:
        log_seq = seq
        skip_len = 0
        method_name = '原始数据'
    log_seq_len = int(len(log_seq))
    
    # step2: 高斯滤波获取三周期对应的序列以及预测结果
    predict_result = np.zeros([log_seq_len+predict_len,len_per])
    for iPeriod in range(len_per):
        predict_result[:,iPeriod] = gauss_wave_predict_py(log_seq,periods[iPeriod],fft_size,predict_len,gauss_alpha)
    
    # step3: 样本内回归，获取回归系数
    Y_now = log_seq
    regress_result = np.zeros([row,col])
    # 单变量回归
    for i in range(len_per):
        X_ori = predict_result[:log_seq_len,i]
        X_now = sm.add_constant(X_ori)
        model_now = sm.OLS(Y_now,X_now)
        res_now = model_now.fit()
        regress_result[i,0:2] = res_now.params[:]
        regress_result[i,-2] = res_now.rsquared
        regress_result[i,-1] = res_now.f_pvalue
    # 多变量回归
    X_ori = predict_result[:log_seq_len,:]
    X_now = sm.add_constant(X_ori)
    model_now = sm.OLS(Y_now,X_now)
    res_now = model_now.fit()
    regress_result[-1,:1+len_per] = res_now.params[:]
    regress_result[-1,-2] = res_now.rsquared
    regress_result[-1,-1] = res_now.f_pvalue
    out_regress_index_name[1+(iAsset)*row-1] = asset_name[iAsset]
    out_regress_value[1+(iAsset)*row-1:(iAsset+1)*row,:] = regress_result
    X_fit = sm.add_constant(predict_result)
    params_beta = np.reshape(res_now.params,[len_per+1,1])
    Y_fit_raw = X_fit@params_beta
    Y_fit = np.reshape(Y_fit_raw,[np.size(Y_fit_raw,0),])
    
    # step4: 将资产序列回归预测结果写入文件
    output = np.zeros([seq_len+predict_len,3+len_per])
    output[:,:] = np.nan
    output_columns = np.full((3+len_per,),'',dtype=np.object_)
    output_columns[0] = asset_name[iAsset]
    output_columns[1] = method_name
    for i in range(len_per):
        output_columns[i+2] = str(periods[i])+'个月高斯滤波'
    output_columns[-1] = '回归拟合曲线'
    
    # 设置数据
    output[:int(seq_len),0] = seq
    output[skip_len:seq_len,1] = log_seq
    output[skip_len:,2:2+len_per] = predict_result
    output[skip_len:,-1] = Y_fit
    # 将数据保存至文件
    df_output = pd.DataFrame(output,index=all_dates,columns=output_columns)
    df_output.to_excel(writer,sheet_name=asset_name[iAsset])

# 将回归系数写入文件
df_regress = pd.DataFrame(out_regress_value,index=out_regress_index_name,columns=out_regress_col_name)
df_regress.to_excel(writer,sheet_name='回归系数')
writer.save()
writer.close()

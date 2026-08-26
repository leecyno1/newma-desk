function output = gauss_wave_predict(wave,period,n_fft,n_predict,gauss_alpha)
% -------------------------------------------------------------------------
% 高斯滤波提取特定周期成分，通过前向补零提升分辨率
% [输入]
% wave：       输入序列，为列向量
% period：     需要提取的周期长度，单位为月
% n_fft：      FFT长度，也即填0后的长度
% n_predict：  外延预测的长度
% gauss_alpha：高斯滤波器带宽
% [输出]
% output：滤波提取的目标周期成分，长度为输入长度+n_predict
% -------------------------------------------------------------------------

% 1、填充0
wave_pad = [zeros(n_fft-length(wave),1); wave];

% 2、进行FFT变换
wave_fft = fft(wave_pad, n_fft);

% 3、生成高斯滤波频率响应，注意这里只刻画了低频部分，后续做共轭对称处理
gauss_index = 1:n_fft;
center_frequency = n_fft / period + 1;
gauss_win = exp(-(gauss_index - center_frequency).^2 / gauss_alpha^2)';

% 4、频域滤波，因为时域为实数，所以频域序列有共轭对称的属性
wave_filter = wave_fft .* gauss_win;
if mod(n_fft,2)==0
    wave_filter((n_fft/2+2):n_fft)=conj(wave_filter((n_fft/2):-1:2));
else
    wave_filter((n_fft-1)/2+2:n_fft)=conj(wave_filter((n_fft-1)/2+1:-1:2));
end

% 5、逆傅里叶变换得到时域还原序列，外延预测本质上是在延拓主值序列
ret = real(ifft(wave_filter));
output = [ret(end-length(wave)+1:end); ret(1:n_predict)];
    
end

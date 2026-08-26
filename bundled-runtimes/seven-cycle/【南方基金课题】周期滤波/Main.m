% -------------------------------------------------------------------------
% 对资产序列做高斯滤波，提取目标周期，并对原始序列做回归
% 注意：默认输入的资产序列是时间对齐的且均为有效数据
% -------------------------------------------------------------------------
clear; clc; close all;

%% -----------------------------------------------------------------
% 设置参数
% -------------------------------------------------------------------------
% 文件名和标签名，如果只有一个标签，指定参数为1即可
file_name = 'data';
sheet_name = 1;

% 预处理，none-不作处理，zero-零均值，detrend-去趋势，YoY-对数同比
% 对于股票指数类数据，自身包含趋势项，采用对数同比处理
% 对于宏观指标数据，因为已经是同比数据，可进行零均值或去趋势项处理
method = 'YoY';  

% 高斯滤波目标周期，可以任意设置周期个数
periods = [42 100 200];   

% 预测长度，单位为月
predict_len = 12;

% FFT长度
fft_size = 4096;   

% 高斯滤波器带宽
gauss_alpha = 10; 

% 文件保存名
save_file_name = [file_name '-' strjoin(sprintfc('%g',periods),'-') '.xlsx'];

%% -----------------------------------------------------------------
% 读取数据
% -------------------------------------------------------------------------
% 读取数据文件
[num,~,raw] = xlsread([file_name '.xlsx'], sheet_name);

% 日期转换为格式 yyyy-mm
dates = raw(2:end,1);
func = @(x) datestr(datenum(x),'yyyy-mm');
dates = cellfun(func,dates, 'UniformOutput', false);

% 获取数据
assets = raw(1,2:end);
asset_num = length(assets);
data = cell2mat(raw(2:end,2:end));

%% -----------------------------------------------------------------
% 遍历每个资产，进行高斯滤波，并将结果写入文件
% -------------------------------------------------------------------------
result = cell(1,asset_num); % 初始化结果储存器
row = 1 + length(periods); % 单变量回归+汇总回归
col = 3 + length(periods); % 截距 + 回归系数 + R2 + P值
out_regress = cell(row*asset_num+1, col+1);
out_regress(1,1:2) = {'品种','Intercept'};
for iCell = 3:3+length(periods)-1
    out_regress{1,iCell} = ['Beta' num2str(iCell-3+1)];
end
out_regress(1,end-1:end)={'R2','P-Value'};
for iAsset = 1:asset_num
    % step1:对数据进行预处理
    seq = data(:,iAsset);
    valid_index = ~isnan(seq);
    seq = seq(valid_index);
    seq_dates = dates(valid_index);
    seq_len = length(seq);
    if strcmp(method, 'YoY')
        log_seq = log(seq(13:end) ./ seq(1:end-12));
        skip_len = 12;
        method_name = '同比处理';
    elseif strcmp(method, 'zero')
        log_seq = seq - mean(seq);
        skip_len = 0;
        method_name = '零均值';
    elseif strcmp(method, 'detrend')
        log_seq = detrend(seq);
        skip_len = 0;
        method_name = '去趋势';
    else
        log_seq = seq;
        skip_len = 0;
        method_name = '原始数据';
    end
    log_seq_len = length(log_seq);
    
    % step2:高斯滤波获取三周期对应的序列以及预测结果
    predict_result = zeros(log_seq_len + predict_len, length(periods));
    for iPeriod = 1:length(periods)
        predict_result(:,iPeriod) = gauss_wave_predict(...
            log_seq, periods(iPeriod), fft_size, predict_len, gauss_alpha);
    end
    
    % step3:样本内回归，获取回归系数 
    Y = log_seq;
    regress_result = zeros(row,col);
    % 单变量回归
    for i =1:length(periods)
        X = [ones(log_seq_len,1) predict_result(1:log_seq_len,i)];
        [b, ~, ~, ~, stats] = regress(Y, X);
        regress_result(i,1:2) = b;
        regress_result(i,end-1:end) = stats([1 3]);
    end
    % 多变量回归
    X = [ones(log_seq_len,1) predict_result(1:log_seq_len,:)];
    [b, ~, ~, ~, stats] = regress(Y, X);
    regress_result(end,1:1+length(periods)) = b;
    regress_result(end,end-1:end) = stats([1 3]);
    out_regress(2+(iAsset-1)*row,1) = assets(iAsset);
    out_regress(2+(iAsset-1)*row:1+iAsset*row,2:end) = num2cell(regress_result);
    
    % step4:将资产序列回归预测结果写入文件
    output = cell(seq_len+predict_len+1, 4+length(periods));
    output(1,1) = {'Date'};
    output(1,2) = assets(iAsset);
    output(1,3) = cellstr(method_name);
    for i = 1:length(periods)
        output(1,3+i) = {[num2str(periods(i)) '个月高斯滤波']};
    end
    output(1,end) = {'回归拟合曲线'};
    % 生成日期
    output(2:seq_len+1,1) = seq_dates; 
    prev_date = seq_dates(end);
    for iDate = 1:predict_len
        date_vec = datevec(prev_date);
        date_vec(2) = date_vec(2) + 1;
        prev_date = datestr(date_vec,'yyyy-mm');
        output(seq_len+1+iDate,1) = cellstr(prev_date);
    end
    % 设置数据
    output(2:seq_len+1,2) = num2cell(seq);
    output(skip_len+2:seq_len+1,3) = num2cell(log_seq);
    output(skip_len+2:end,4:3+length(periods)) = num2cell(predict_result);
    output(skip_len+2:end,end) = num2cell([ones(log_seq_len+predict_len,1) predict_result]*b);
    result{iAsset} = output;
    xlswrite(save_file_name, output, assets{iAsset});
end

% 回归系数写入文件
xlswrite(save_file_name, out_regress, '回归系数');
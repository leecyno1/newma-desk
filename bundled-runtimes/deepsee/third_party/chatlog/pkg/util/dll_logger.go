package util

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// DLLLogger DLL日志记录器
type DLLLogger struct {
	mu        sync.Mutex
	logFile   *os.File
	logPath   string
	enabled   bool
}

var (
	dllLogger     *DLLLogger
	dllLoggerOnce sync.Once
)

// GetDLLLogger 获取DLL日志记录器单例
func GetDLLLogger() *DLLLogger {
	dllLoggerOnce.Do(func() {
		dllLogger = &DLLLogger{
			enabled: true,
		}
		// 尝试初始化日志文件
		dllLogger.initLogFile()
	})
	return dllLogger
}

// initLogFile 初始化日志文件
func (l *DLLLogger) initLogFile() {
	if !l.enabled {
		return
	}

	// 使用默认工作目录
	workDir := DefaultWorkDir("")

	// 创建日志目录
	logDir := filepath.Join(workDir, "log")
	if err := os.MkdirAll(logDir, 0755); err != nil {
		// 如果创建目录失败，禁用日志
		l.enabled = false
		return
	}

	// 生成日志文件名：dll.log (不再使用时间戳，以便于查找，或者保持追加模式)
	logFileName := "dll.log"
	l.logPath = filepath.Join(logDir, logFileName)

	// 创建日志文件
	file, err := os.OpenFile(l.logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		l.enabled = false
		return
	}

	l.logFile = file
}

// LogError 记录错误信息
func (l *DLLLogger) LogError(message string) {
	l.log("ERROR", message)
}

// LogStatus 记录状态信息
func (l *DLLLogger) LogStatus(level int, message string) {
	var levelStr string
	switch level {
	case 0:
		levelStr = "INFO"
	case 1:
		levelStr = "SUCCESS"
	case 2:
		levelStr = "ERROR"
	default:
		levelStr = "UNKNOWN"
	}
	l.log(levelStr, message)
}

// LogInfo 记录普通信息
func (l *DLLLogger) LogInfo(message string) {
	l.log("INFO", message)
}

// LogDebug 记录调试信息
func (l *DLLLogger) LogDebug(message string) {
	l.log("DEBUG", message)
}

// LogWarning 记录警告信息
func (l *DLLLogger) LogWarning(message string) {
	l.log("WARNING", message)
}

// log 内部日志记录函数
func (l *DLLLogger) log(level, message string) {
	if !l.enabled || l.logFile == nil {
		return
	}

	l.mu.Lock()
	defer l.mu.Unlock()

	timestamp := time.Now().Format("2006-01-02 15:04:05.000")
	logEntry := fmt.Sprintf("[%s] [%s] %s\n", timestamp, level, message)

	if _, err := l.logFile.WriteString(logEntry); err != nil {
		// 写入失败，关闭文件并禁用日志
		l.logFile.Close()
		l.logFile = nil
		l.enabled = false
	}
}

// GetLogPath 获取日志文件路径
func (l *DLLLogger) GetLogPath() string {
	return l.logPath
}

// IsEnabled 检查日志是否启用
func (l *DLLLogger) IsEnabled() bool {
	return l.enabled
}

// Close 关闭日志文件
func (l *DLLLogger) Close() {
	l.mu.Lock()
	defer l.mu.Unlock()

	if l.logFile != nil {
		l.logFile.Close()
		l.logFile = nil
	}
	l.enabled = false
}

// LogInitialization 记录DLL初始化信息
func (l *DLLLogger) LogInitialization(pid uint32, success bool, errorMsg string) {
	if success {
		l.LogStatus(1, fmt.Sprintf("DLL初始化成功，PID: %d", pid))
	} else {
		l.LogError(fmt.Sprintf("DLL初始化失败，PID: %d, 错误: %s", pid, errorMsg))
	}
}

// LogPolling 记录轮询信息
func (l *DLLLogger) LogPolling(keyFound bool, key string, keyType string) {
	if keyFound {
		l.LogStatus(1, fmt.Sprintf("找到%s密钥: %s", keyType, key))
	} else {
		l.LogStatus(0, "轮询中...")
	}
}

// LogCleanup 记录清理信息
func (l *DLLLogger) LogCleanup() {
	l.LogStatus(0, "DLL资源已清理")
}
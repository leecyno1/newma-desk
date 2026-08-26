package darwin

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/rs/zerolog/log"
	"github.com/shirou/gopsutil/v4/process"

	"github.com/sjzar/chatlog/internal/wechat/model"
	"github.com/sjzar/chatlog/pkg/appver"
)

const (
	V4ProcessName = "WeChat"
	V4DBFile      = "db_storage/session/session.db"
)

// Detector implements WeChat process detection on macOS (darwin).
type Detector struct{}

func NewDetector() *Detector { return &Detector{} }

func (d *Detector) FindProcesses() ([]*model.Process, error) {
	processes, err := process.Processes()
	if err != nil {
		log.Err(err).Msg("获取进程列表失败")
		return nil, err
	}

	var result []*model.Process
	for _, p := range processes {
		name, err := p.Name()
		if err != nil {
			continue
		}
		name = strings.TrimSuffix(name, ".app")
		if name != V4ProcessName {
			continue
		}

		exe, _ := p.Exe()

		info := &model.Process{
			PID:      uint32(p.Pid),
			ExePath:  exe,
			Platform: "darwin",
			Status:   model.StatusOffline,
		}

		if ver, err := appver.New(exe); err == nil {
			info.Version = ver.Version
			info.FullVersion = ver.FullVersion
		} else {
			log.Debug().Err(err).Msgf("读取应用版本失败: %s", exe)
		}

		// Fill DataDir / AccountName if possible.
		if err := initializeProcessInfo(p, info); err != nil {
			log.Debug().Err(err).Msgf("获取进程 %d 信息失败", p.Pid)
		}

		result = append(result, info)
	}

	return result, nil
}

// initializeProcessInfo tries to infer WeChat data dir and account name from open files.
func initializeProcessInfo(p *process.Process, info *model.Process) error {
	files, err := p.OpenFiles()
	if err != nil {
		// Process exists but may not have opened DB files yet (not logged in).
		info.AccountName = fmt.Sprintf("未登录微信_%d", p.Pid)
		return nil
	}

	dbPath := filepath.FromSlash(V4DBFile)
	for _, f := range files {
		if strings.HasSuffix(f.Path, dbPath) {
			parts := strings.Split(f.Path, string(filepath.Separator))
			if len(parts) < 4 {
				continue
			}
			info.Status = model.StatusOnline
			info.DataDir = strings.Join(parts[:len(parts)-3], string(filepath.Separator))
			info.AccountName = parts[len(parts)-4]
			return nil
		}
	}

	info.AccountName = fmt.Sprintf("未登录微信_%d", p.Pid)
	return nil
}


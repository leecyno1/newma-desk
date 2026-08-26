package process

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/shirou/gopsutil/v4/process"
)

// CheckSingleInstance checks if another instance is running using a PID file.
// If another instance is found, it prompts the user to force close it.
// Returns a cleanup function to be called on exit.
func CheckSingleInstance(workDir string) (func(), error) {
	if err := os.MkdirAll(workDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create work dir: %w", err)
	}
	pidFile := filepath.Join(workDir, "chatlog.pid")

	// Read existing PID file
	if content, err := os.ReadFile(pidFile); err == nil {
		pidStr := strings.TrimSpace(string(content))
		if pid, err := strconv.Atoi(pidStr); err == nil {
			if pid != os.Getpid() {
				if exists, _ := process.PidExists(int32(pid)); exists {
					if isSameExecutable(pid) {
						fmt.Printf("Detected another instance running (PID: %d).\n", pid)
						fmt.Print("Do you want to force close it and continue? [y/N]: ")

						reader := bufio.NewReader(os.Stdin)
						input, _ := reader.ReadString('\n')
						input = strings.TrimSpace(strings.ToLower(input))

						if input == "y" || input == "yes" {
							if p, err := process.NewProcess(int32(pid)); err == nil {
								if err := p.Kill(); err != nil {
									return nil, fmt.Errorf("failed to kill process: %w", err)
								}
								fmt.Println("Process killed.")
							} else {
								fmt.Println("Process not found, continuing...")
							}
						} else {
							return nil, fmt.Errorf("application already running")
						}
					} else {
						os.Remove(pidFile)
					}
				}
			}
		}
	}

	// Write current PID
	currentPID := os.Getpid()
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(currentPID)), 0644); err != nil {
		return nil, fmt.Errorf("failed to write pid file: %w", err)
	}

	// Cleanup function
	return func() {
		os.Remove(pidFile)
	},
	nil
}

func isSameExecutable(pid int) bool {
	currentExe, err := os.Executable()
	if err != nil {
		currentExe = ""
	}
	currentBase := strings.ToLower(filepath.Base(currentExe))

	p, err := process.NewProcess(int32(pid))
	if err != nil {
		return false
	}
	if exe, err := p.Exe(); err == nil && exe != "" {
		if currentExe != "" && strings.EqualFold(exe, currentExe) {
			return true
		}
		if currentBase != "" && strings.EqualFold(filepath.Base(exe), currentBase) {
			return true
		}
	}
	if name, err := p.Name(); err == nil && name != "" {
		name = strings.TrimSuffix(strings.ToLower(name), ".exe")
		base := strings.TrimSuffix(currentBase, ".exe")
		if base != "" && name == base {
			return true
		}
	}
	return false
}

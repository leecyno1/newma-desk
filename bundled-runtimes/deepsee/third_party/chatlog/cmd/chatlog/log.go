package chatlog

import (
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/sjzar/chatlog/pkg/util"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"github.com/sirupsen/logrus"
	"github.com/spf13/cobra"
)

var Debug bool

func initLog(cmd *cobra.Command, args []string) {
	zerolog.SetGlobalLevel(zerolog.InfoLevel)

	if Debug {
		zerolog.SetGlobalLevel(zerolog.DebugLevel)
	}

	logDir := filepath.Join(util.DefaultWorkDir(""), "log")
	_ = util.PrepareDir(logDir)
	logFile := filepath.Join(logDir, "chatlog.log")
	logFD, err := os.OpenFile(logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, os.ModePerm)

	writers := []io.Writer{zerolog.ConsoleWriter{Out: os.Stderr, TimeFormat: time.RFC3339}}
	if err == nil {
		writers = append(writers, zerolog.ConsoleWriter{Out: logFD, NoColor: true, TimeFormat: time.RFC3339})
	}

	log.Logger = log.Output(io.MultiWriter(writers...))
}

func initTuiLog(cmd *cobra.Command, args []string) {
	logDir := filepath.Join(util.DefaultWorkDir(""), "log")
	_ = util.PrepareDir(logDir)
	logFile := filepath.Join(logDir, "chatlog.log")
	logFD, err := os.OpenFile(logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, os.ModePerm)

	logOutput := io.Discard
	if err == nil {
		logOutput = logFD
	}

	log.Logger = log.Output(zerolog.ConsoleWriter{Out: logOutput, NoColor: true, TimeFormat: time.RFC3339})
	logrus.SetOutput(logOutput)
}

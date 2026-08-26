//go:build !windows

package windows

import (
	"context"
	"fmt"

	"github.com/sjzar/chatlog/internal/wechat/decrypt"
	"github.com/sjzar/chatlog/internal/wechat/model"
)

// DLLExtractor is a stub implementation for non-Windows builds.
// The real implementation relies on wx_key.dll and golang.org/x/sys/windows.
type DLLExtractor struct {
	validator *decrypt.Validator
}

func IsDLLAvailable() bool { return false }

func NewDLLV4Extractor() *DLLExtractor { return &DLLExtractor{} }

func (e *DLLExtractor) Extract(ctx context.Context, proc *model.Process) (string, string, error) {
	return "", "", fmt.Errorf("wx_key.dll extractor is only available on Windows")
}

func (e *DLLExtractor) SearchKey(ctx context.Context, memory []byte) (string, bool) {
	return "", false
}

func (e *DLLExtractor) SetValidate(validator *decrypt.Validator) {
	e.validator = validator
}


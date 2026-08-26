package windows

import (
	"context"

	"github.com/sjzar/chatlog/internal/wechat/decrypt"
	"github.com/sjzar/chatlog/pkg/util"
)

type V4Extractor struct {
	validator *decrypt.Validator
	logger    *util.DLLLogger
}

func NewV4Extractor() *V4Extractor {
	return &V4Extractor{
		logger: util.GetDLLLogger(),
	}
}

func (e *V4Extractor) SearchKey(ctx context.Context, memory []byte) (string, bool) {
	// TODO : Implement the key search logic for V4
	return "", false
}

func (e *V4Extractor) SetValidate(validator *decrypt.Validator) {
	e.validator = validator
}

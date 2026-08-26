package mcp

import (
	"fmt"
)

// enum ErrorCode {
// 	// Standard JSON-RPC error codes
// 	ParseError = -32700,
// 	InvalidRequest = -32600,
// 	MethodNotFound = -32601,
// 	InvalidParams = -32602,
// 	InternalError = -32603
// }

// Error
type Error struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

var (
	ErrParseError     = &Error{Code: -32700, Message: "Parse error"}
	ErrInvalidRequest = &Error{Code: -32600, Message: "Invalid Request"}
	ErrMethodNotFound = &Error{Code: -32601, Message: "Method not found"}
	ErrInvalidParams  = &Error{Code: -32602, Message: "Invalid params"}
	ErrInternalError  = &Error{Code: -32603, Message: "Internal error"}

	ErrInvalidSessionID = &Error{Code: 400, Message: "Invalid session ID"}
	ErrSessionNotFound  = &Error{Code: 404, Message: "Could not find session"}
	ErrTooManyRequests  = &Error{Code: 429, Message: "Too many requests"}
)

func (e *Error) Error() string {
	return fmt.Sprintf("%d: %s", e.Code, e.Message)
}

func (e *Error) JsonRPC() Response {
	return Response{
		JsonRPC: JsonRPCVersion,
		Error:   e,
	}
}

func NewErrorResponse(id interface{}, code int, err error) *Response {
	return &Response{
		JsonRPC: JsonRPCVersion,
		ID:      id,
		Error: &Error{
			Code:    code,
			Message: err.Error(),
		},
	}
}

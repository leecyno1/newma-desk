package mcp

import (
	"encoding/json"
	"io"

	"github.com/gin-gonic/gin"
)

type Session struct {
	id string
	w  io.Writer
	c  *ClientInfo
}

func NewSession(c *gin.Context, id string) *Session {
	return &Session{
		id: id,
		w:  NewSSEWriter(c, id),
	}
}

func (s *Session) Write(p []byte) (n int, err error) {
	return s.w.Write(p)
}

func (s *Session) WriteError(req *Request, err error) {
	resp := NewErrorResponse(req.ID, 500, err)
	b, err := json.Marshal(resp)
	if err != nil {
		return
	}
	s.Write(b)
}

func (s *Session) WriteResponse(req *Request, data interface{}) error {
	resp := NewResponse(req.ID, data)
	b, err := json.Marshal(resp)
	if err != nil {
		return err
	}
	s.Write(b)
	return nil
}

func (s *Session) SaveClientInfo(c *ClientInfo) {
	s.c = c
}

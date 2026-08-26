package mcp

import (
	"io"
	"net/http"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/rs/zerolog/log"
)

const (
	ProcessChanCap = 1000
)

type MCP struct {
	sessions  map[string]*Session
	sessionMu sync.Mutex

	ProcessChan chan ProcessCtx
}

func NewMCP() *MCP {
	return &MCP{
		sessions:    make(map[string]*Session),
		ProcessChan: make(chan ProcessCtx, ProcessChanCap),
	}
}

func (m *MCP) HandleSSE(c *gin.Context) {
	id := uuid.New().String()
	m.sessionMu.Lock()
	m.sessions[id] = NewSession(c, id)
	m.sessionMu.Unlock()

	c.Stream(func(w io.Writer) bool {
		<-c.Request.Context().Done()
		return false
	})

	m.sessionMu.Lock()
	delete(m.sessions, id)
	m.sessionMu.Unlock()
}

func (m *MCP) GetSession(id string) *Session {
	m.sessionMu.Lock()
	defer m.sessionMu.Unlock()
	return m.sessions[id]
}

func (m *MCP) HandleMessages(c *gin.Context) {

	// panic("xxx")

	// 啊这, 一个 sessionid 有 3 种写法 session_id, sessionId, sessionid
	// 官方 SDK 是 session_id: https://github.com/modelcontextprotocol/python-sdk/blob/c897868/src/mcp/server/sse.py#L98
	// 写的是 sessionId: https://github.com/modelcontextprotocol/inspector/blob/aeaf32f/server/src/index.ts#L157

	sessionID := c.Query("session_id")
	if sessionID == "" {
		sessionID = c.Query("sessionId")
	}
	if sessionID == "" {
		sessionID = c.Param("sessionid")
	}
	if sessionID == "" {
		c.JSON(http.StatusBadRequest, ErrInvalidSessionID.JsonRPC())
		c.Abort()
		return
	}

	session := m.GetSession(sessionID)
	if session == nil {
		c.JSON(http.StatusNotFound, ErrSessionNotFound.JsonRPC())
		c.Abort()
		return
	}

	var req Request
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, ErrInvalidRequest.JsonRPC())
		c.Abort()
		return
	}

	log.Debug().Msgf("session: %s, request: %s", sessionID, req)
	select {
	case m.ProcessChan <- ProcessCtx{Session: session, Request: &req}:
	default:
		c.JSON(http.StatusTooManyRequests, ErrTooManyRequests.JsonRPC())
		c.Abort()
		return
	}

	c.String(http.StatusAccepted, "Accepted")
}

func (m *MCP) Close() {
	close(m.ProcessChan)
}

type ProcessCtx struct {
	Session *Session
	Request *Request
}

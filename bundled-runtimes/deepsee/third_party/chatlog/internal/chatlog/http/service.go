package http

import (
	"context"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mark3labs/mcp-go/server"
	"github.com/rs/zerolog/log"

	"github.com/sjzar/chatlog/internal/chatlog/database"
	"github.com/sjzar/chatlog/internal/errors"
)

type Subscription struct {
	Talker     string    `json:"talker"`
	WebhookURL string    `json:"webhook_url"`
	LastTime   time.Time `json:"last_time"`
	LastStatus string    `json:"last_status"`
	LastError  string    `json:"last_error"`
}

type Service struct {
	conf Config
	db   *database.Service

	router *gin.Engine
	server *http.Server

	mcpServer           *server.MCPServer
	mcpSSEServer        *server.SSEServer
	mcpStreamableServer *server.StreamableHTTPServer

	// MCP 实时消息订阅
	mcpSubscriptions map[string]*Subscription
	mcpSubMu         sync.RWMutex

	// md5 到 path 的缓存（用于图片、视频等媒体文件）
	md5PathCache map[string]string
	md5PathMu    sync.RWMutex

	lastPushTime   time.Time
	lastPushTalker string

	subscriptionPath string
}

type Config interface {
	GetHTTPAddr() string
	GetDataDir() string
	GetSaveDecryptedMedia() bool
}

func NewService(conf Config, db *database.Service) *Service {
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()

	// Handle error from SetTrustedProxies
	if err := router.SetTrustedProxies(nil); err != nil {
		log.Err(err).Msg("Failed to set trusted proxies")
	}

	// Middleware
	router.Use(
		errors.RecoveryMiddleware(),
		errors.ErrorHandlerMiddleware(),
		gin.LoggerWithWriter(log.Logger, "/health"),
		corsMiddleware(),
	)

	s := &Service{
		conf:             conf,
		db:               db,
		router:           router,
		mcpSubscriptions: make(map[string]*Subscription),
		md5PathCache:     make(map[string]string),
		subscriptionPath: filepath.Join(conf.GetDataDir(), "subscriptions.json"),
	}

	s.loadSubscriptions()
	s.initMCPServer()
	s.initRouter()
	return s
}

func (s *Service) saveSubscriptions() {
	s.mcpSubMu.RLock()
	defer s.mcpSubMu.RUnlock()

	data, err := json.MarshalIndent(s.mcpSubscriptions, "", "  ")
	if err != nil {
		log.Error().Err(err).Msg("Failed to marshal subscriptions")
		return
	}

	if err := os.WriteFile(s.subscriptionPath, data, 0644); err != nil {
		log.Error().Err(err).Msg("Failed to save subscriptions")
	}
}

func (s *Service) loadSubscriptions() {
	s.mcpSubMu.Lock()
	defer s.mcpSubMu.Unlock()

	data, err := os.ReadFile(s.subscriptionPath)
	if err != nil {
		if !os.IsNotExist(err) {
			log.Error().Err(err).Msg("Failed to read subscriptions file")
		}
		return
	}

	if err := json.Unmarshal(data, &s.mcpSubscriptions); err != nil {
		log.Error().Err(err).Msg("Failed to unmarshal subscriptions")
	}
}

func (s *Service) Start() error {

	s.server = &http.Server{
		Addr:    s.conf.GetHTTPAddr(),
		Handler: s.router,
	}

	go func() {
		// Handle error from Run
		if err := s.server.ListenAndServe(); err != nil {
			log.Err(err).Msg("Failed to start HTTP server")
		}
	}()

	log.Info().Msg("Starting HTTP server on " + s.conf.GetHTTPAddr())

	return nil
}

func (s *Service) ListenAndServe() error {

	s.server = &http.Server{
		Addr:    s.conf.GetHTTPAddr(),
		Handler: s.router,
	}

	log.Info().Msg("Starting HTTP server on " + s.conf.GetHTTPAddr())
	return s.server.ListenAndServe()
}

func (s *Service) Stop() error {

	if s.server == nil {
		return nil
	}

	// 使用超时上下文优雅关闭
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	if err := s.server.Shutdown(ctx); err != nil {
		log.Debug().Err(err).Msg("Failed to shutdown HTTP server")
		return nil
	}

	log.Info().Msg("HTTP server stopped")
	return nil
}

func (s *Service) updateSubscriptionStatus(talker, status, errMsg string) {
	s.mcpSubMu.Lock()
	if sub, ok := s.mcpSubscriptions[talker]; ok {
		sub.LastStatus = status
		sub.LastError = errMsg
	}
	s.mcpSubMu.Unlock()
	s.saveSubscriptions()
}

func (s *Service) GetRouter() *gin.Engine {
	return s.router
}

func (s *Service) GetMCPSubscriptions() []*Subscription {
	s.mcpSubMu.RLock()
	defer s.mcpSubMu.RUnlock()
	res := make([]*Subscription, 0, len(s.mcpSubscriptions))
	for _, sub := range s.mcpSubscriptions {
		res = append(res, &Subscription{
			Talker:     sub.Talker,
			WebhookURL: sub.WebhookURL,
			LastTime:   sub.LastTime,
			LastStatus: sub.LastStatus,
			LastError:  sub.LastError,
		})
	}
	return res
}

func (s *Service) GetMCPStatus() (time.Time, string) {
	s.mcpSubMu.RLock()
	defer s.mcpSubMu.RUnlock()
	return s.lastPushTime, s.lastPushTalker
}

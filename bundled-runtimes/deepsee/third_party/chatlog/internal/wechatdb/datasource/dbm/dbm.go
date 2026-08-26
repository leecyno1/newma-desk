package dbm

import (
	"database/sql"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
	_ "github.com/mattn/go-sqlite3"
	"github.com/rs/zerolog/log"

	"github.com/sjzar/chatlog/internal/errors"
	"github.com/sjzar/chatlog/pkg/filecopy"
	"github.com/sjzar/chatlog/pkg/filemonitor"
)

type DBManager struct {
	path       string
	id         string
	walEnabled bool
	fm         *filemonitor.FileMonitor
	fgs        map[string]*filemonitor.FileGroup
	dbs        map[string]*sql.DB
	dbPaths    map[string][]string
	mutex      sync.RWMutex
}

func NewDBManager(path string, walEnabled bool) *DBManager {
	return &DBManager{
		path:       path,
		id:         filepath.Base(path),
		walEnabled: walEnabled,
		fm:         filemonitor.NewFileMonitor(),
		fgs:        make(map[string]*filemonitor.FileGroup),
		dbs:        make(map[string]*sql.DB),
		dbPaths:    make(map[string][]string),
	}
}

func (d *DBManager) AddGroup(g *Group) error {
	fg, err := filemonitor.NewFileGroup(g.Name, d.path, g.Pattern, g.BlackList)
	if err != nil {
		return err
	}
	fg.AddCallback(d.Callback)
	d.fm.AddGroup(fg)
	d.mutex.Lock()
	d.fgs[g.Name] = fg
	d.mutex.Unlock()
	return nil
}

func (d *DBManager) AddCallback(group string, callback func(event fsnotify.Event) error) error {
	d.mutex.RLock()
	fg, ok := d.fgs[group]
	d.mutex.RUnlock()
	if !ok {
		return errors.FileGroupNotFound(group)
	}
	fg.AddCallback(callback)
	return nil
}

func (d *DBManager) GetDB(name string) (*sql.DB, error) {
	dbPaths, err := d.GetDBPath(name)
	if err != nil {
		return nil, err
	}
	return d.OpenDB(dbPaths[0])
}

func (d *DBManager) GetDBs(name string) ([]*sql.DB, error) {
	dbPaths, err := d.GetDBPath(name)
	if err != nil {
		return nil, err
	}
	dbs := make([]*sql.DB, 0)
	for _, file := range dbPaths {
		db, err := d.OpenDB(file)
		if err != nil {
			return nil, err
		}
		dbs = append(dbs, db)
	}
	return dbs, nil
}

func (d *DBManager) GetDBPath(name string) ([]string, error) {
	d.mutex.RLock()
	dbPaths, ok := d.dbPaths[name]
	d.mutex.RUnlock()
	if !ok {
		d.mutex.RLock()
		fg, ok := d.fgs[name]
		d.mutex.RUnlock()
		if !ok {
			return nil, errors.FileGroupNotFound(name)
		}
		list, err := fg.List()
		if err != nil {
			return nil, errors.DBFileNotFound(d.path, fg.PatternStr, err)
		}
		if len(list) == 0 {
			return nil, errors.DBFileNotFound(d.path, fg.PatternStr, nil)
		}
		dbPaths = filterPrimaryDBs(list)
		d.mutex.Lock()
		d.dbPaths[name] = dbPaths
		d.mutex.Unlock()
	}
	return dbPaths, nil
}

func (d *DBManager) OpenDB(path string) (*sql.DB, error) {
	d.mutex.RLock()
	db, ok := d.dbs[path]
	d.mutex.RUnlock()
	if ok {
		return db, nil
	}
	var err error
	tempPath := path
	if runtime.GOOS == "windows" {
		tempPath, err = filecopy.GetTempCopy(d.id, path)
		if err != nil {
			log.Err(err).Msgf("获取临时拷贝文件 %s 失败", path)
			return nil, err
		}
	}
	db, err = sql.Open("sqlite3", tempPath)
	if err != nil {
		log.Err(err).Msgf("连接数据库 %s 失败", path)
		return nil, err
	}
	d.mutex.Lock()
	d.dbs[path] = db
	d.mutex.Unlock()
	return db, nil
}

func (d *DBManager) Callback(event fsnotify.Event) error {
	if !(event.Op.Has(fsnotify.Create) || event.Op.Has(fsnotify.Write) || event.Op.Has(fsnotify.Rename)) {
		return nil
	}

	basePath := normalizeDBPath(event.Name)
	d.mutex.Lock()
	db, ok := d.dbs[basePath]
	if ok {
		delete(d.dbs, basePath)
		go func(db *sql.DB) {
			time.Sleep(time.Second * 5)
			db.Close()
		}(db)
	}
	if (event.Op.Has(fsnotify.Create) || event.Op.Has(fsnotify.Rename)) && isPrimaryDBFile(event.Name) {
		d.dbPaths = make(map[string][]string)
	}
	d.mutex.Unlock()

	return nil
}

func (d *DBManager) Start() error {
	return d.fm.Start()
}

func (d *DBManager) Stop() error {
	return d.fm.Stop()
}

func (d *DBManager) Close() error {
	for _, db := range d.dbs {
		db.Close()
	}
	return d.fm.Stop()
}

func normalizeDBPath(path string) string {
	if strings.HasSuffix(path, "-wal") || strings.HasSuffix(path, "-shm") {
		return strings.TrimSuffix(strings.TrimSuffix(path, "-wal"), "-shm")
	}
	return path
}

func isPrimaryDBFile(path string) bool {
	return strings.HasSuffix(path, ".db") && !strings.HasSuffix(path, ".db-wal") && !strings.HasSuffix(path, ".db-shm")
}

func filterPrimaryDBs(paths []string) []string {
	result := make([]string, 0, len(paths))
	for _, path := range paths {
		if isPrimaryDBFile(path) {
			result = append(result, path)
		}
	}
	return result
}

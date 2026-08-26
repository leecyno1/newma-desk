package model

import (
	"path/filepath"
	"regexp"
)

type MediaV4 struct {
	Type         string `json:"type"`
	Key          string `json:"key"`
	Dir1         string `json:"dir1"`
	Dir2         string `json:"dir2"`
	ExtraBuffer  string `json:"extraBuffer"` // Extra buffer for Rec subdirectory
	Name         string `json:"name"`
	Size         int64  `json:"size"`
	ModifyTime   int64  `json:"modifyTime"`
}

func (m *MediaV4) Wrap() *Media {

	var path string
	switch m.Type {
	case "image":
		// Clean extra_buffer: extract only alphanumeric characters
		extraBuffer := m.cleanExtraBuffer(m.ExtraBuffer)
		if extraBuffer != "" {
			// Path with Rec/{extra_buffer}: msg/attach/{Dir1}/{Dir2}/Rec/{extraBuffer}/Img/{Name}
			path = filepath.Join("msg", "attach", m.Dir1, m.Dir2, "Rec", extraBuffer, "Img", m.Name)
		} else {
			// Fallback to old path format: msg/attach/{Dir1}/{Dir2}/Img/{Name}
			path = filepath.Join("msg", "attach", m.Dir1, m.Dir2, "Img", m.Name)
		}
	case "video":
		path = filepath.Join("msg", "video", m.Dir1, m.Name)
	case "file":
		path = filepath.Join("msg", "file", m.Dir1, m.Name)
	}

	return &Media{
		Type:       m.Type,
		Key:        m.Key,
		Path:       path,
		Name:       m.Name,
		Size:       m.Size,
		ModifyTime: m.ModifyTime,
	}
}

// cleanExtraBuffer extracts only alphanumeric characters from extra_buffer
func (m *MediaV4) cleanExtraBuffer(extraBuffer string) string {
	if extraBuffer == "" {
		return ""
	}

	// Remove all non-alphanumeric characters
	re := regexp.MustCompile(`[^a-zA-Z0-9]`)
	cleaned := re.ReplaceAllString(extraBuffer, "")

	// Only return if we have meaningful content
	if cleaned != "" {
		return cleaned
	}

	return ""
}

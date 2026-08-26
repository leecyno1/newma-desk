package repository

import (
	"context"

	"github.com/sjzar/chatlog/internal/model"
)

func (r *Repository) GetMedia(ctx context.Context, _type string, key string) (*model.Media, error) {
	return r.ds.GetMedia(ctx, _type, key)
}

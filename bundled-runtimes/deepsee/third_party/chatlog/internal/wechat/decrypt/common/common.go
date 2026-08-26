package common

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"encoding/binary"
	"fmt"
	"hash"
	"io"
	"os"

	"github.com/sjzar/chatlog/internal/errors"
)

const (
	KeySize      = 32
	SaltSize     = 16
	AESBlockSize = 16
	SQLiteHeader = "SQLite format 3\x00"
	IVSize       = 16
)

type DBFile struct {
	Path       string
	Salt       []byte
	TotalPages int64
	FirstPage  []byte
}

func OpenDBFile(dbPath string, pageSize int) (*DBFile, error) {
	fp, err := os.Open(dbPath)
	if err != nil {
		return nil, errors.OpenFileFailed(dbPath, err)
	}
	defer fp.Close()

	fileInfo, err := fp.Stat()
	if err != nil {
		return nil, errors.StatFileFailed(dbPath, err)
	}

	fileSize := fileInfo.Size()
	totalPages := fileSize / int64(pageSize)
	if fileSize%int64(pageSize) > 0 {
		totalPages++
	}

	buffer := make([]byte, pageSize)
	n, err := io.ReadFull(fp, buffer)
	if err != nil {
		return nil, errors.ReadFileFailed(dbPath, err)
	}
	if n != pageSize {
		return nil, errors.IncompleteRead(fmt.Errorf("read %d bytes, expected %d", n, pageSize))
	}

	if bytes.Equal(buffer[:len(SQLiteHeader)-1], []byte(SQLiteHeader[:len(SQLiteHeader)-1])) {
		return nil, errors.ErrAlreadyDecrypted
	}

	return &DBFile{
		Path:       dbPath,
		Salt:       buffer[:SaltSize],
		FirstPage:  buffer,
		TotalPages: totalPages,
	}, nil
}

func XorBytes(a []byte, b byte) []byte {
	result := make([]byte, len(a))
	for i := range a {
		result[i] = a[i] ^ b
	}
	return result
}

func ValidateKey(page1 []byte, key []byte, salt []byte, hashFunc func() hash.Hash, hmacSize int, reserve int, pageSize int, deriveKeys func([]byte, []byte) ([]byte, []byte)) bool {
	if len(key) != KeySize {
		return false
	}

	_, macKey := deriveKeys(key, salt)

	mac := hmac.New(hashFunc, macKey)
	dataEnd := pageSize - reserve + IVSize
	mac.Write(page1[SaltSize:dataEnd])

	pageNoBytes := make([]byte, 4)
	binary.LittleEndian.PutUint32(pageNoBytes, 1)
	mac.Write(pageNoBytes)

	calculatedMAC := mac.Sum(nil)
	storedMAC := page1[dataEnd : dataEnd+hmacSize]

	return hmac.Equal(calculatedMAC, storedMAC)
}

func DecryptPage(pageBuf []byte, encKey []byte, macKey []byte, pageNum int64, hashFunc func() hash.Hash, hmacSize int, reserve int, pageSize int) ([]byte, error) {
	offset := 0
	if pageNum == 0 {
		offset = SaltSize
	}

	mac := hmac.New(hashFunc, macKey)
	mac.Write(pageBuf[offset : pageSize-reserve+IVSize])

	pageNoBytes := make([]byte, 4)
	binary.LittleEndian.PutUint32(pageNoBytes, uint32(pageNum+1))
	mac.Write(pageNoBytes)

	hashMac := mac.Sum(nil)

	hashMacStartOffset := pageSize - reserve + IVSize
	hashMacEndOffset := hashMacStartOffset + hmacSize

	if !bytes.Equal(hashMac, pageBuf[hashMacStartOffset:hashMacEndOffset]) {
		return nil, errors.ErrDecryptHashVerificationFailed
	}

	iv := pageBuf[pageSize-reserve : pageSize-reserve+IVSize]
	block, err := aes.NewCipher(encKey)
	if err != nil {
		return nil, errors.DecryptCreateCipherFailed(err)
	}

	mode := cipher.NewCBCDecrypter(block, iv)

	encrypted := make([]byte, pageSize-reserve-offset)
	copy(encrypted, pageBuf[offset:pageSize-reserve])

	mode.CryptBlocks(encrypted, encrypted)

	decryptedPage := append(encrypted, pageBuf[pageSize-reserve:pageSize]...)

	return decryptedPage, nil
}

package errors

import "net/http"

func OpenFileFailed(path string, cause error) *Error {
	return Newf(cause, http.StatusInternalServerError, "failed to open file: %s", path).WithStack()
}

func StatFileFailed(path string, cause error) *Error {
	return Newf(cause, http.StatusInternalServerError, "failed to stat file: %s", path).WithStack()
}

func ReadFileFailed(path string, cause error) *Error {
	return Newf(cause, http.StatusInternalServerError, "failed to read file: %s", path).WithStack()
}

func IncompleteRead(cause error) *Error {
	return New(cause, http.StatusInternalServerError, "incomplete header read during decryption").WithStack()
}

func WriteOutputFailed(cause error) *Error {
	return New(cause, http.StatusInternalServerError, "failed to write output").WithStack()
}

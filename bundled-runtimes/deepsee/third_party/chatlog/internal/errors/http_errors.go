package errors

import "net/http"

func InvalidArg(arg string) error {
	return Newf(nil, http.StatusBadRequest, "invalid argument: %s", arg)
}

func HTTPShutDown(cause error) error {
	return Newf(cause, http.StatusInternalServerError, "http server shut down")
}

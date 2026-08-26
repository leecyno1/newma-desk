import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.tushare_service import TushareDataService


def main():
    with patch("services.tushare_service.ts.pro_api", return_value=object()) as pro_api:
        service = TushareDataService(token="test", mock_mode=False)
    assert service.request_timeout_seconds == 8
    pro_api.assert_called_once_with("test", timeout=8)

    with (
        patch.dict(os.environ, {"TUSHARE_REQUEST_TIMEOUT_SECONDS": "4"}),
        patch("services.tushare_service.ts.pro_api", return_value=object()) as short_pro_api,
    ):
        service = TushareDataService(token="test", mock_mode=False)
    assert service.request_timeout_seconds == 4
    short_pro_api.assert_called_once_with("test", timeout=4)
    print("OK Tushare requests use a bounded timeout for interactive fund analysis")


if __name__ == "__main__":
    main()

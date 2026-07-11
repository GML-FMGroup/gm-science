#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/start-gm-science.sh"
STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
  echo "gm-science 已退出。按回车关闭这个窗口。"
else
  echo "gm-science 启动失败，错误码：$STATUS"
  echo "按回车关闭这个窗口。"
fi
read -r _
exit "$STATUS"

# 真实眼控到无线通知联调

2026-10-29：SSH已确认PYNQ启动；bootpy和eye-control自启保持关闭。DONE/用户LED不再自动呈现旧演示灯态，不能仅凭灯未亮判断Linux未启动。FPGA manager state=unknown不作为故障结论；本轮未加载位流。

真实眼控发送已增加明确log/live选项，默认off，模型、识别门限、位流和语音素材未改。只消费DwellController的live选择，记录源帧/采样时间/会话/序号/code/重试及回执；日志有界且报告丢弃数。非阻塞轮询，失联选择不积压后补发，暂停/取消/退出停止待发及重试。已发送事件无法撤销，ACK只证明接纳，不代表动作完成。

项目目录中运行，不可与其他硬件程序或服务并行：

```bash
# 离线预检，不加载硬件、不发消息
bash tools/run_eye.sh --profile data/private/profiles/startup_check.json --eye-events log --check-only
# 接线及三端核对完成、用户坐好后，运行60秒真实眼控到远端日志
bash tools/run_eye.sh --profile data/private/profiles/startup_check.json --eye-events log
# 队友LIVE接入已确认、外设适合操作后才启用
bash tools/run_eye.sh --profile data/private/profiles/current_eye.json --eye-events live
```

log模式的输入仍是真实视线选择；线协议TEST=1，只打印事件，不调用队友动作接口。可验证真实选择到无线接收，不能充当LIVE动作验收。live模式TEST=0，接收端必须实现eye_accept_button；原弱实现回BUSY，不假报成功。已有启动服务默认关闭无线，配置文件也不能暗中启用。

用户于2026-10-29更新：三个接收端均已由队友合入交接包，统一按地址末字节02/03/04区分；历史固件目录名保留。合并后固件尚未经本端读取或联调，保留队友程序。队友暂不方便测试，按用户要求暂停无线联调，等用户通知再恢复。A独立USB供电，UART三线当前是否已复核接好尚未明确确认。PYNQ新启动已SSH确认，boot_id=ada9f486-2e1b-404a-ac2d-2debeb634381；眼控/演示inactive、disabled，SSH已关闭，未启动测试。已安装补丁、源文件哈希一致，默认off/显式log及独立识别证据预检通过。完整真人无线链路仍待实测。

源码：src/eye_tracker/trial_events.py、event_link.py、appearance_trial.py、board.py、launch.py。原版备份及补丁：build/deploy/eye_wireless_20261029。312项软件回归通过（新增10项含运行循环验证）；这些是模拟传输测试，不是射频或真人验收。

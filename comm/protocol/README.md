# 眼控按钮事件协议 v1

范围：PYNQ → 本端BearPi UART1 → SLE → 队友BearPi。只交付已完成停留的按钮事件。队友负责动作。当前已有PYNQ实现、Python参考接收器和可移植C99接收器；C接收器已接入BearPi UART1/SLE项目源码，见../firmware/README.md；2026-10-27已通过PYNQ-UART-A-B/C/D三端TEST台架验证；实际动作与真实眼控到无线未验收，见../HANDOFF.md。

## 事件与传输

| code | 含义 |
| --- | --- |
| 1 | water / 喝水 |
| 2 | rest / 休息 |
| 3 | help / 帮助 |
| 4 | more / 进入更多页 |
| 5 | back / 返回主页面 |

4、5是界面导航事件，不自行定义成电机等动作。辅助BTN0–BTN3管理本地暂停、取消、清校准、退出，不冒充这五个选择事件。

UART：3.3V，115200 bit/s，8位数据、无校验、1位停止，无硬件流控。当前50MHz AXI UART Lite分频约115740.7 bit/s（相对115200约+0.47%），对端设115200。接收FIFO16字节，所以协议固定16字节，始终最多一项请求在途；桥接端不得往事件UART夹带调试日志、广播或多份确认。

| 字节偏移 | 长度 | 内容 |
| --- | --- | --- |
| 0 | 2 | A5 5A |
| 2 | 1 | 版本01 |
| 3 | 1 | HELLO=01，PING=02，EVENT=10，ACK=80（十六进制） |
| 4 | 4 | session，非零uint32，小端 |
| 8 | 4 | sequence，uint32，小端；HELLO为0，随后请求递增，不回绕 |
| 12 | 1 | EVENT为上述code，HELLO/PING为0，ACK原样回显请求code |
| 13 | 1 | 请求：0正式、1合成测试；ACK：状态码 |
| 14 | 2 | 对前14字节做CRC-16/CCITT-FALSE，结果小端 |

CRC多项式0x1021、初值0xFFFF、不反射、xorout=0；ASCII `123456789` 得0x29B1。固定示例见vectors.json。接收是字节流，不能假定一次串口回调就是一包；用eye_feed逐字节处理。

ACK状态：0接收成功，1重复已接收（不再交付动作），2没有该会话，3旧序号或同序号不同内容，4非法事件，5模式不符，6应用接收接口未就绪/队列满（BUSY）。ACK仅由最终接收端生成，本端中继不能在仅收到UART时假报成功。它表示接收端校验并接纳事件，不表示动作模块执行完成。

## 状态和失败处理

- 新连接先HELLO，正常500ms空闲发送PING。接收器连续2000ms无有效请求即失去会话；SLE断开时立即eye_disconnect并清空收发队列。
- 首次发送前事件年龄最多150ms。正常一次选择产生一次事件；心跳在途时最多暂存一项仍新鲜的选择。断线或另一个EVENT在途时拒收新选择，不留离线积压。
- 确认等待180ms后重发同一帧，最多3次发送，总请求时限600ms。这些是初始联调参数，不是已实测星闪延迟指标。
- 重发始终保持session/sequence不变。接收端用当前会话的最高序号及上一帧内容去重，重复HELLO不能清除去重状态；旧事件不再交付。有效包校验后，再由集成层接纳到其处理接口。
- 暂停、取消、清校准、退出、输入失效、UART错误或服务间隔超过250ms，清掉未发事件并停止重试；重新连接后不自动补发旧选择。已经发出的事件无法撤回。超时但曾发送的结果记为delivery_unknown，不能声称对端没收到。
- C参考实现先更新去重状态并给出deliver标记；项目eye_endpoint.c在候选副本上运行它，仅在应用回调接纳成功后提交状态。回调拒收返回6/BUSY并保留原序号，不ACK后丢弃；长时间动作交由队友的独立任务执行。
- 不承诺接收端断电重启期间的持久化“恰好一次”，也不提供认证/防恶意重放。中继必须丢弃掉线积压，不做离线存储转发。若以后用于有风险动作，需要队友独立互锁，通信取消不等于物理急停。
- 正式接收器默认拒绝TEST=1。测试接收器开启allow_test后，合成事件仅进日志/测试处理器，不驱动实际动作模块。

## 文件和复现

PYNQ：src/eye_tracker/event_protocol.py、event_uart.py、event_link.py。C接口：eye_event.h/.c；host_check.c只是电脑验证程序。C接口不依赖LiteOS/SDK，现由固件工作任务调用，SLE回调仅复制数据，ACK经SLE原路返回。

在项目根目录执行 `python tools/verify_event_c.py`，使用本机现有Vivado MinGW GCC编译C程序，与Python比较实际字节输出。结果在comm/build/protocol/result.json；这不是无线测试。

已有板端诊断仅在显式 `--event-test` 时发送合成按钮；默认ui-test/control-test均不开事件UART。例如准备好**测试模式接收器**、新固件及接线并确认板卡独占后：

```sh
bash tools/run_board.sh ui-test --load --event-test --output data/private/event_ui
bash tools/run_board.sh control-test --load --seconds 120 --audible --event-test --output data/private/event_controls
```

控制与传输状态保存在event_trace.json/controls_trace.json/result.json。当前界面的选中提示只代表本地选择，远端送达状态以通信日志为准；正式整机集成时需补送达/失败显示。日志和构建均不能替代真实眼控验证。

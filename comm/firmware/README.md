# BearPi 按钮事件固件

2026-10-27：当前为四板版本，A是主动连接的SLE Client，B/C/D是三个独立SLE Server。固定SDK提交08d2880956249642cc90d7eae9b80ed721646967，参考其中sle_uart_1_vs_8拓扑。四份包已烧录并通过三端TEST台架验收：85次协议事务、38个新事件及B断电恢复；接纳依据与范围见../HANDOFF.md和../build/network_20261027/result.json。旧单链路版本保存在comm/build/single_peer_verified_20261027。

## 角色与接线

| 板 | 编译参数 | 节点号 | 无线地址最后一字节 |
| --- | --- | --- | --- |
| A，PYNQ旁 | bridge | 0 | 01 |
| B，接收端 | receiver --node B | 1 | 02 |
| C，接收端 | receiver --node C | 2 | 03 |
| D，接收端 | receiver --node D | 3 | 04 |

名字eye_event_v2，地址前缀E1:59:00:00:00。三端代码相同，节点号各自不同，不可把同一接收包烧到三块板。固定地址只用于本组台架，不是身份认证。

A的UART1：115200/8N1，GPIO15/TXD发送、GPIO16/RXD接收。PYNQ Arduino AR1/D1接A的RXD，AR0/D0接TXD，GND接GND。只连这三线，两板独立供电，不接电源脚；PYNQ USB Host保留。接收端不初始化UART1；UART0均用于USB下载和日志。

## 向队友交付的接口

按钮代码：1喝水、2休息、3帮助、4更多、5返回。每个事件都发给B/C/D，具体动作由队友定义。

TEST=1只打印`EYE TEST node=... session=... seq=... code=...`，不会驱动外设。正式TEST=0调用eye_app.h的`int eye_accept_button(const eye_packet *event)`；当前弱实现返回0/BUSY=6，因此测试包不假报正式动作接纳。

队友提供该函数的强实现，并将其.c文件加入comm/build_sle.py的项目files列表，同时在linked_sample_members预期列表加入对应的.c.obj；保持唯一eye_entry启动入口，详细说明见../HANDOFF.md。函数在EyeEvent任务中执行，应立即把code/session/sequence复制进有界工作队列，成功返回1，模块未就绪或队列满返回0。不能保留event指针、等待耗时动作完成或在这里直接执行动作；另一个工作任务消费队列。只有成功接纳才提交去重状态，相同session/sequence重试不再次入队。队友自有程序须合并本模块和唯一启动入口，不可单独刷回旧程序后仍期待通信生效。

ACK表示接收接口接纳，不表示动作完成。三端分发不是原子事务：某一端失败时，其余端可能已接纳，无法回滚；本地取消也不能撤回远端已接纳的事件。去重只覆盖当前供电会话，不保证跨断电的持久化恰好一次。若动作需要执行完成反馈或幂等，应由动作模块增加对应机制。

## 三端确认与失效处理

A默认required_mask=0x7，B/C/D对应1/2/4。只有三个连接都完成发现和订阅才向主程序报READY；每个请求按连接身份收集确认，全部接纳才返回成功。乱序确认、重复确认、无关连接不能伪造全组成功。`EYE GROUP ... accepted=0x7 required=0x7 status=0`表示本次三端接纳；错误状态不等于全部接纳。

请求从首次收到起600ms截止；有限重试只补尚未确认的端。连接代次变化或离线清除未完成请求，不维护离线事件队列；重新上线需新HELLO会话。已经部分接纳的动作不撤回。PYNQ超时只可视为交付结果不确定，不能视作从未执行。

无线回调只复制数据，业务任务5ms轮询；每连接独立发送缓冲，确认或500ms超时后才释放/断开。接收积压100ms丢弃，UART半包30ms超时。启动设置失败、回调队列溢出等致命错误保持未就绪，需要复位排查，不无限重启。MTU520来自固定SDK支持范围，业务帧仍16字节。

UART使用FULL_OR_SUFFICIENT_DATA_OR_IDLE阈值1；旧FULL_OR_IDLE对16字节帧曾积满128字节才交付，已经单链路实物验证修复。

## 构建与验证

按顺序构建，勿与HiSpark IDE同时编译：

```powershell
& '<user-home>/AppData/Local/Programs/Python/Python311/python.exe' -B 'D:/Eye_tracker_system/comm/build_sle.py' bridge
& '<user-home>/AppData/Local/Programs/Python/Python311/python.exe' -B 'D:/Eye_tracker_system/comm/build_sle.py' receiver --node B
& '<user-home>/AppData/Local/Programs/Python/Python311/python.exe' -B 'D:/Eye_tracker_system/comm/build_sle.py' receiver --node C
& '<user-home>/AppData/Local/Programs/Python/Python311/python.exe' -B 'D:/Eye_tracker_system/comm/build_sle.py' receiver --node D
```

各自产物comm/build/network/A、B、C、D中的ws63-liteos-app_all.fwpkg和result.json。脚本临时替换SDK CMake入口后恢复，重建确切libsamples.a，核对五个项目对象和唯一eye_entry，防止旧官方示例残留。server/client参数保留官方UART0基线。--required CD或C仅供明确标记的台架子集，生产默认BCD，不能自动降级。

主机检查：tools/verify_radio.py（50场景/6877断言）、tools/verify_fanout.py（169检查）、tools/verify_firmware.py（121检查）。结果分别在comm/build/radio_host、fanout、endpoint。这些模拟回调/真实C协议检查不替代实物射频、UART和实际动作验收。

烧录用项目内comm/tools/BurnTool，WS63芯片模式13、COM9、115200下载；实际板身份必须按A/B/C/D标签确认。COM17是PYNQ，勿刷。烧录完成关闭串口后才开启启动日志；不要同时运行两个串口工具，不使用Erase all或eFuse操作。四板先用TEST日志验收，再交给队友接入正式动作。

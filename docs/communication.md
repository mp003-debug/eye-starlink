# PYNQ 与小熊派星闪通信

2026-10-27一发三收台架通信已通过：A/B/C/D均烧录并核对节点身份，PYNQ经UART向A发送TEST事件，A汇总B/C/D三端确认。三轮85次协议事务成功，38个新事件；84次首发、1次重试成功。D端38条事件逐项核对无重复，B/C接纳依据为已核对代码的三端汇总ACK，未同时采集B/C事件串口。3个坏CRC包无回复、3个旧序号被拒绝；B断电时握手和事件各3次尝试无回执，重新上电自动恢复，D未补收离线事件。请求到轮询读出ACK为73.37–255.37ms（含重试），不是眼控或动作延迟。C/D分别断电、长时间无线及真实眼控到无线尚未验收。首次直接MMIO遇Bus error，显式加载已验证UART位流并配置50/100MHz时钟后通过；诊断入口已修正且复核。四板源码/固件和接入说明见comm/HANDOFF.md，证据comm/build/network_20261027/result.json。当前TEST只打印日志，正式LIVE仍须队友接入有界动作队列。PYNQ空闲、串口/SSH关闭，A/B/C独立供电、D接电脑，三线不动、补光灯断电。

当前接线、四板角色、构建命令、接收钩子和故障语义见[固件接入说明](../comm/firmware/README.md)。16字节PYNQ协议保持不变，见[按钮协议](../comm/protocol/README.md)。

## 历史单链路证据（以下配置不用于新四板包）


## 当前拓扑与接线核对（2026-10-27）

用户已有A/B/C/D四块相同BearPi-Pico H3863。A接PYNQ，B/C/D接收同一事件，队友分别实现动作。下文Oct26结果仍只适用于A/B单连接；当前烧录的固件不是一发三收固件。

实物照片已读清并与官方原理图EXT GPIO核对：

| PYNQ Arduino丝印 | A板背面丝印 | A板信号 |
| --- | --- | --- |
| AR1 / D1（TX） | RXD | GPIO16 / UART1_RX |
| AR0 / D0（RX） | TXD | GPIO15 / UART1_TX |
| GND | GND | 共地 |

按用户第三张照片方向，AR0/AR1是右侧下方8孔Arduino插座的最下孔/倒数第二孔；不要使用更外侧的双排树莓派接口。第一张A板背面照片USB在下，左侧中部GND、RXD、TXD三个相邻针可用。RXD/TXD是外引UART1，芯片UART0另接CH340用于USB调试。

两板断电后接线；只接三根信号线，独立供电，不连接5V/3V3/VSYS/VUSB。PYNQ为母插座、A为公排针，需要公对母杜邦线；已确认有三根公对母线及四板供电条件；C/D暂未焊排针，无线验证不需要排针。照片和原理图证据在comm/build/wiring_20261027；用户已确认断电接线及重新开机，A/C单接收端TEST与完整回执已通过，见下方最新进展。

一发三收实现约定（待开发/上板，不是当前功能）：B/C/D采用独立节点身份与无线地址；A按连接分别发送和接收ACK；三端各自按session/sequence去重。只有三个最终接收接口均确认才报告全部送达；掉线或超时记录具体未确认端，已送达端不回滚、不重复触发，不自动补发过期动作。不能承诺三块同时执行或跨掉电恰好一次。队友只接入接收回调/有界队列，不修改可靠传输层；ACK是接纳，不是动作完成。

验证顺序：A/C单接收端UART及TEST已通过 → 三接收端固件/独立身份 → 四板同时收件、重试去重、逐端断线恢复和不补发 → 交接源码、固件、三线接法、事件表/回调范例与实测结果。完成通信后回到眼控长时间运行和独立启动，不重复已经通过的普通短试用。


更新：2026-10-26。两块BearPi-Pico H3863（WS63/Hi3863）已到货，排针已焊、USB数据线和杜邦线齐全。约2米、无遮挡，PYNQ只发送已完成停留的按钮事件，队友负责动作。USB Host继续保留给有线鼠标。

2026-10-27上板进展：PYNQ→UART→A→星闪→C→回执的单接收端测试已通过。B板保留队友墨水屏程序，C已烧录项目接收固件。定位并修复A板UART只在128字节满缓冲才交付的问题，改用FULL_OR_SUFFICIENT_DATA_OR_IDLE；9次握手/心跳全部往返，动态界面6次合成选择全部收到最终确认。另55次协议事务通过：26个新TEST事件、26次重复ACK、2次HELLO、1次旧序号拒收；另注入1个坏CRC包未获回复，随后正确包成功。该组全部首发收到回执，测得请求到轮询读出ACK为71.24–101.35ms，不是眼控端到端延迟。当前bridge包SHA a1831f68271fbed15df45aab948b3921d414951881cf96e6266c2e210c25a367，receiver仍为dd1e8b80…。新UART位流相机/UI/静音音频回归已通过；本轮没有真人眼控或外设动作验收。12份新传输文件哈希核对，DMA正常停止、无复位恢复、最终mem/uio占用为空，COM9监听和烧录器已关闭；PYNQ空闲，A接电脑、C独立供电、三线不动、灯断电。三接收端和当前固件事件级断线重连仍待实现/验证。详细证据comm/build/uart_20261027/result.json。

## 已完成和验证边界

2026-10-26通信更新：两块BearPi已烧录项目固件，星闪配对、服务发现和订阅就绪已通过。B板复位后A板记录DOWN→READY，随后30秒无新故障；这是建链/重连验收，尚未发送按钮包。修复SDK增量归档残留旧示例和MTU64不符合SDK范围两个问题；现在使用官方示例MTU520，按钮协议仍为16字节。23场景/2674项主机断言通过。A板接电脑COM9、B板独立USB供电，尚未连接PYNQ杜邦线；PYNQ仍用原音频位流、补光灯断电。下一步核对UART引脚，验证新UART位流及真实消息/最终ACK，再接真实眼控。实测记录：comm/build/hardware_20261026/result.json。

- HiSpark Studio1.0.0.6、环境包v1.0.3、Python3.11、CMake/Ninja、RISC-V编译器与CH340驱动可用。用户更新WSL3.0.3后确认弹窗消失。实际构建走Windows原生工具链，不需要另装Ubuntu；HiSpark程序文件未修改。
- SDK：comm/sdk，官方仓库https://gitee.com/bearpi/bearpi-pico_h3863.git，固定提交08d2880956249642cc90d7eae9b80ed721646967。
- 实际Vivado工程已加入Arduino UART，AXI UART Lite在0x42C00000，50MHz、115200/8N1。新bit/HWH构建通过，WNS2.002ns、WHS0.031ns，LUT4433、FF6206、BRAM40，DRC0错误。新UART位流已完成上述相机/UI/静音音频回归；A/C单接收端TEST及回执已通过。
- PYNQ发送器、16字节按钮协议、C接收器已实现；本轮已集成独立UART1和SLE，**bridge和receiver两份项目固件均完成编译打包**。官方UART0示例留在comm/build/server、client作为基线，不是本轮项目固件。
- 161项Python软件回归通过；C/Python比对1368条响应一致；实际C端点121项断言通过；无线适配器使用真实SDK声明和模拟底层回调，两角色23场景、2674项断言通过。分别见build/software、comm/build/protocol、endpoint、radio_host。
- SLE建链/订阅和一次B板复位恢复已验证；A/C实物UART及TEST/重复ACK已通过；三端消息、当前固件事件级重连不重放及真实眼控事件仍待验证。SDK日志保留既有Kconfig/NV及第三方编译警告，不宣称零警告。

| 角色 | 固件 | 字节数 | SHA256 |
| --- | --- | --- | --- |
| bridge | comm/build/bridge/ws63-liteos-app_all.fwpkg | 1431720 | `a1831f68271fbed15df45aab948b3921d414951881cf96e6266c2e210c25a367` |
| receiver | comm/build/receiver/ws63-liteos-app_all.fwpkg | 1429800 | `dd1e8b8021692c3a776618040bc6628fff22ef908614df0532cbe8100f20d45f` |

两端目录均保存ELF、mconfig、配置、源文件哈希及result.json，日志为comm/build/bridge.log、receiver.log。已核对固件/源码哈希和ELF项目入口。当前SDK工作配置为bridge；构建临时CMake入口已恢复官方内容。

## 接线与运行职责

| PYNQ-Z2 Arduino口 | PYNQ旁的BearPi UART1 |
| --- | --- |
| D1 / TX，FPGA U12 | GPIO16 / RX |
| D0 / RX，FPGA T14 | GPIO15 / TX |
| GND | GND |

3.3V逻辑，只连TX/RX/GND、交叉收发；两板独立供电，不连接电源脚。到货后按实物丝印与官方图确认GPIO位置，不能把GPIO、排针编号及FPGA封装脚混为一谈。相机继续用Pmod，PYNQ USB Host保留。接收端当前不初始化UART1，队友模块接口由其决定；两块小熊派UART0均留作USB日志/下载。

本端桥接器只转发完整请求和匹配ACK。最终接收端校验、去重，成功接纳后返回ACK。UART中断和SLE回调只复制数据，不执行耗时动作。断线清队列，过期包不补发；错误不会被当作成功。

**当前固件TEST消息仅打印日志。正式事件接收钩子eye_accept_button默认返回BUSY，等待队友接入有界接收队列后再启用正式交付。** ACK只代表接收接口接纳，不能代表动作执行完成。更多=4、返回=5是导航事件。接口、源文件分工、超时及启动失败处理详见[固件接入说明](../comm/firmware/README.md)，线协议见[按钮协议](../comm/protocol/README.md)。

无线名字和地址固定给本项目一对演示板使用，不提供身份认证；不承诺断电重启前后的持久化恰好一次。正常断线后恢复广播/扫描；未连接时的启动设置失败保持未就绪并提示复位。实际行为须到货验证。

## 复现构建

逐个执行，不与IDE同时编译。脚本不烧录、不改全局PATH；SDK源入口临时替换后恢复，配置切换到所选角色。

```powershell
& '<user-home>/AppData/Local/Programs/Python/Python311/python.exe' -B 'D:/Eye_tracker_system/comm/build_sle.py' bridge
& '<user-home>/AppData/Local/Programs/Python/Python311/python.exe' -B 'D:/Eye_tracker_system/comm/build_sle.py' receiver
```

server/client参数仍用于构建官方UART0基线。原始LED示例配置保存在comm/build/official_original.config。

## 实物联调顺序

1. 已完成：两端烧录、READY及一次B板复位恢复。A接电脑COM9、B独立USB供电；电脑仅一个空余USB口，轮流烧录即可。
2. 核对接线后先做PYNQ UART回环/单跳，再接无线两板；新UART位流回归相机、显示、AUX音频。
3. 显式--event-test发送合成五类按钮，检查对应日志、重复抑制、丢确认重试和断线重连不重放；界面的选中提示目前只表示本地选择，远端送达以日志为准。
4. 与队友约定接收接口后验证正式事件；再由真实眼控触发。链路验收与眼控验收分别记录。

眼控现状：普通室内光、当次校准、有限头动的真实四区域选择及本地语音已通过阶段检查；补光灯保持断电。连续运行、冷启动和独立启动仍待完成，见docs/status.md。

依据：[PYNQ官方引脚约束](https://github.com/Xilinx/PYNQ/blob/master/boards/Pynq-Z2/base/vivado/constraints/base.xdc)、[AMD PG142](https://docs.amd.com/v/u/en-US/pg142-axi-uartlite)、本地固定提交SDK公开API与[小熊派SLE示例说明](https://www.bearpi.cn/core_board/bearpi/pico/h3863/software/SLE串口透传测试.html)。

烧录操作记录：仅使用项目内comm/tools/BurnTool副本，烧录前将configure/config_chip_type.ini显式设为WS63（CurrentChipTypeId=13），再核对目标角色与包SHA256。工具退出后曾观察到该值回到3，不能依赖上次选择。使用-console记录完成标志，921600下载、115200日志；在连接提示后按住RST约1秒再松开，成功后自动切换串口监听。未连接PYNQ，COM17是PYNQ调试口，不得作为小熊派烧录目标。

# 必要时重建BearPi固件

当前集成优先使用已通过短时联调的四份固件，不需要重新安装IDE或SDK。
本包是应用源码/config/固件交接，不是包含全部SDK的独立工程，也没有在本轮重编固件。

固定SDK：HiSpark/fbb_ws63，tag 1.10.106，commit 7cda10e7476d8df35f0ac1a4013eb395874247e0。
本机保底SDK在D:/Eye_tracker_system/comm/fbb_sdk（源码子目录src）；只能只读复用/复制，不能在那里构建升级产物。
升级目录原comm/sdk来自另一基线，不能因为版本宏相同就直接使用。重建时在升级目录准备独立同提交SDK，
核对sdk_lock.json的18项选定文件哈希；18项一致不等于整仓库一致。

## 构建输入映射

| 节点 | 应用树 | 全量配置 | 分支/对象 |
| --- | --- | --- | --- |
| 01 | central01/application/.../sle_uart | config/01/ws63_liteos_app.config | EYE_A_CONTROL；5个通信对象 |
| 02 | receivers/application/.../sle_uart | config/02/ws63_liteos_app.config | EYE_LINK + NODE_B；home + care_hmi |
| 03 | 同一receivers应用树 | config/03/ws63_liteos_app.config | EYE_LINK + NODE_C；wearable + epd |
| 04 | 同一receivers应用树 | config/04/ws63_liteos_app.config | EYE_LINK + NODE_D；wearable + epd |

把所选应用树覆盖到**独立SDK副本**的src/application/samples/products/sle_uart。
将build_hooks/products_CMakeLists.txt、products_Kconfig分别放到父目录products的CMakeLists.txt、Kconfig；
如副本已有自己的入口，应合并，保证最终只编入一个项目应用入口。
把该节点完整config放到src/build/config/target_config/ws63/menuconfig/acore/ws63_liteos_app.config。
mconfig.h是实际构建生成的核对参考，不应当作手写头文件覆盖SDK生成流程。

用已安装的Python/CMake/Ninja/RISC-V工具链，在独立SDK的src目录执行已采用的干净构建命令：

```text
python -B build.py ws63-liteos-app -ninja -j6 -release -c
```

原实际构建脚本位于保底comm/integration/four_board_20261030/build_node.py，仅供只读参考，
**不要直接运行它**：脚本路径固定到保底SDK。升级项目可在独立目录参数化重建流程。
干净构建前检查独立output中没有旧libsamples.a残留，ar增量替换不会自动移除旧成员。
01应仅有eye_main、eye_radio、eye_endpoint、eye_fanout、eye_event五个对象；
02另加eye_home、care_hmi；03/04另加eye_wearable、wearable_epd。
ELF中应用入口只应有__zinitcall_run_eye_entry；核对节点宏、c=0x205/p=0x215、UART和新接线定义。

新构建产物保留完整fwpkg、ELF/map、config、源清单、构建日志和SHA256；不能要求新编译哈希必然等于历史包。
本包只携带运行/恢复所需fwpkg；原完整ELF/map和日志仍在保底对应build目录，可追溯。
烧录时用HiSpark BurnTool、芯片WS63（工具配置CurrentChipTypeId=13）、对应地址节点完整包。
日志115200；工具连接后按用户实际操作复位。逐块确认身份，禁止仅凭USB位置/历史COM号判断。
只恢复/升级指定节点，保留外设应用，不用旧TEST-only固件覆盖显示任务。

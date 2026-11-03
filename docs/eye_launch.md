> 升级副本说明（2026-10-29）：下文保留的是原保底板端的运行说明。此副本尚未部署，不能照此安装或覆盖保底服务。升级上板前须先改为独立目录 /home/xilinx/Eye_Tracker_Upgrade_Version、独立服务 eye-control-upgrade.service，并保证与保底程序互斥运行。仅复制本目录不会修改板端。当前先进行本地开发。

# 个人眼控手动启动

2026-10-28用户确定：正常开机后按需启动，开机自动进入程序不作为保底前置项，停止自启重启测试。电脑只发启动命令；采集、识别、显示、停留和本地语音均在PYNQ运行，不依赖Notebook或电脑计算。

最新复测（2026-10-28）：恢复后手动启动完成60.050秒/468帧/20次真实选择，三次更多/返回；用户确认按钮和语音正常、无误选或明显漏响应、画面稳定，与此前20分钟测试感受相近。程序正常结束、双DMA和音频清理通过；本轮未重启、不发送无线。证据见私有release_manual_recheck_20261028及docs/release_baseline.md。

## 当前配置与准备

2026-10-29按用户要求恢复原有开机就绪灯：`bootpy.service`为enabled，`eye-control.service`仍disabled。原脚本加载base.bit，同步闪灯8次后四颗用户灯常亮、两颗RGB灯熄灭；手动执行已成功，用户确认DONE与四颗黄灯亮。此次未重启，下次冷启动尚未重新实测。开机后没有眼控画面是预期。灯提示结束、系统就绪后再手动启动眼控，服务保留等待bootpy与PL状态清理结束的顺序依赖。

使用随板12V/3A电源、J9 REG，电脑MicroUSB供电线断开。保持HDMI OUT、MIC+HP到音箱AUX连接，音箱开机并选AUX；相机位置/镜头不动、补光灯断电。当前无线关闭、UART三线断开。电源和UART接线调整需先正常关机并完全断电。

先等Linux与网络就绪，关闭其他硬件程序/Notebook，按已校准姿势坐好。正常结束会黑屏；音频I2C出错或DMA停止未确认时保留日志，按恢复说明处理，不强制忽略故障。

## 推荐演示流程

从电脑SSH登录板卡（当前地址192.168.2.99），需要开始时执行：

```bash
sudo systemctl start eye-control.service
```

这是手动启动，不会开启下次上电自启。服务在板上运行，关闭日志窗口不会停止服务；全过程计算无需电脑参与。屏幕出现中心圆点后看它约6–10秒，再用视线选择四按钮及返回。当前使用个人`current_eye.json`配置，交互最多20分钟；还没有无限运行模式。

查看状态及本次日志：

```bash
systemctl status eye-control.service --no-pager
sudo journalctl -u eye-control.service -b -n 60 --no-pager
```

需要提前结束可按板上BTN3，或执行：

```bash
sudo systemctl stop eye-control.service
```

服务使用SIGINT走原程序清理、不会超时后SIGKILL强杀DMA进程，也不会循环重启。清理未完成时不要再次加载位流；先检查日志。语义见[systemd终止配置](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)。

## 预检与直接运行

工程路径`/home/xilinx/Eye_tracker_system`。以下只检查路径、位流/HWH/模型哈希与硬件合同，不加载FPGA、不发声、不创建运行记录：

```bash
cd /home/xilinx/Eye_tracker_system
bash tools/run_eye.sh --profile data/private/profiles/current_eye.json --check-only
```

也可在同一目录直接执行，需保持该终端会话；不要与服务同时运行：

```bash
bash tools/run_eye.sh --profile data/private/profiles/current_eye.json
```

推荐演示用前面的手动服务入口，直接运行保留给调试。脚本固定使用PYNQ虚拟环境并申请硬件权限，检查通过不代表当次眼控成功。真正进入选择前仍须通过原独立证据检查与新鲜中心参考。

## 配置、证据与恢复

临时60秒`/etc/systemd/system/eye-control.service.d/startup-check.conf`已撤下，备份于私有`data/private/bringup/release_startup_20261028/retired_startup-check.conf`。有效服务现恢复`current_eye.json`（1200秒、语音开启），主服务仍disabled。按需`start`不会启用上电自动运行。若仍需短测试，可直接选择已有`startup_check.json`，不要再安装自启覆盖。

服务语法、脚本语法、板端干净环境离线预检已通过；识别源码、模型和生产位流未变。先前真人服务热启动完成60.075秒/463帧/21次选择，用户确认四按钮/返回与语音正常；20分钟真实眼控语音已有独立记录。自启冲突及音频无应答的失败证据继续保留，完整断电并关闭演示后手动静音音频检查恢复通过。此前静音恢复本身不是听音验收，随后真人手动复测已通过（见本页顶部），仍未证明唯一电气根因；按用户要求不再继续上电自启验收。

每次运行独立保存`data/private/runs/eye_<时间标签>_<UUID>/`，以`result.json`和`visual_trial.json`判断完成；`launch_profile.json`只证明配置。板卡RTC可能不准，以boot_id、单调时钟和电脑记录日期关联。私有眼图、个人模型及校准不进入公共交付包。

BTN2目前只清除校准并禁止选择，尚不是完整校准向导。个人模型、普通室内光及有限头动仍是使用边界；真实眼控到无线、重新入座适应性与最终提交包另行收口。

厂商就绪灯已按用户要求恢复：只启用原有bootpy.service，未修改原脚本；恢复前副本与结果在data/private/bringup/boot_led_restore_20261029。不要在眼控运行期间手动启动bootpy，它会重载base.bit。下一次手动眼控由项目入口加载自己的位流。若需撤回此次开机灯设置，空闲时执行`sudo systemctl disable bootpy.service`即可；不必改动眼控工程。

# PYNQ 上板：显示与有界重复取帧

本包验证数据通路，尚不是眼控应用。具体位流的构建/板测范围以status.md及build/board/result.json为准，不用上一版短时板测冒充新版通过。

## 接线与唯一控制者

在断电时保持现有摄像头/转接板接线，接好 PYNQ 的 HDMI OUT 到屏幕、网线到电脑，再使用原来适合板卡的供电开机。现在不拆滤片、不添加红外灯。不要运行旧 Notebook、旧眼控程序或其他 overlay。2026-10-20用户已开机。SSH核实：电脑192.168.2.1，板卡192.168.2.99；hostname=pynq、BOARD=Pynq-Z2、兼容zynq-7000。板上Python3.10.4/PYNQ3.1.1/NumPy1.21.5/Pillow9.0.1已读取。

必须先通过 SSH 只读核查系统、当前进程及已有自启服务，确认没有其他程序持有 DMA，再下载位流。Python 进程名称只能提示排查，不能证明 DMA 空闲；本程序的文件锁也只能协调本程序，无法锁住无关 Notebook。不要在运行 Linux 时执行旧 ps7_init 脚本。

本地完整 Vivado 工程仍位于 `D:/Eye_tracker_system/fpga/project/eye_tracker.xpr`。传到板上的 zip 只含诊断运行需要的内容，不替代完整工程交付。

## 部署与只读核查

电脑运行 `python D:/Eye_tracker_system/tools/package_board.py` 可重建 `build/deploy/eye_tracker_board.zip`。将 zip 通过已确认的 SSH 连接传至板卡，在新的 `~/Eye_tracker_system` 目录解压；若已有目录，先检查内容，不能覆盖未知用户文件。解压后的该目录应直接包含 src、tools、docs、build。

从板上的工程目录执行：

```sh
python3 tools/board_probe.py
bash tools/run_board.sh inspect
```

第一条仅输出系统/依赖版本、内存和可能相关的进程名称，不加载 PYNQ、不读写 FPGA 寄存器；第二条校验 bit/HWH 哈希、VDMA 格式和寄存器地址，也不访问 FPGA。运行依赖 Python >=3.8、NumPy、Pillow 和板卡既有 PYNQ 环境。先看版本，不自动升级系统或安装不匹配的软件。若系统 Python 不含 PYNQ，应使用原有 PYNQ 虚拟环境的解释器。

## 分步验证

下面每次 live 命令都会重新下载配套位流，必须在上一命令正常结束且没有其他控制者时运行。本机需要root权限。首次尝试发现sudo默认Python没有PYNQ；改用原虚拟环境后还需要保留XILINX_XRT。run_board.sh只传递PYTHONPATH、XILINX_XRT和BOARD，并保留登录环境选择的解释器，不升级或重装系统。已核实解释器为/usr/local/share/pynq-venv/bin/python3，XILINX_XRT=/usr、BOARD=Pynq-Z2。

1. 屏幕显示路径：物理 SW0 置低，使显示来自 DDR；SW0 置高是独立硬件彩条，不能证明 DDR 显示通过。

```sh
bash tools/run_board.sh display --load --seconds 10
```

观察八色竖条、四边白线及底部黑白细条。核对颜色、边界、宽高比例、闪烁/撕裂和结束后黑屏。HDMI 有效输出是 640×480；屏幕的缩放设置可能影响比例。程序返回 0 只说明程序检查通过，肉眼屏幕检查另行记录。

2. 静态彩色 UI：

```sh
bash tools/run_board.sh display --load --seconds 10 --frame build/deploy/ui_static.rgb565
```

该图保留“模拟”标记，不会响应眼睛，也不发声。当前静态缓冲在运行中不可改写。实时preview模式另用三个独立显示缓冲；不修改这个静态模式的不可变约定。

3. 原装相机单帧：先放普通目标或直尺，稳定室内光照，先在约35–40cm建立焦点基线，再检查30–45cm前后移动的清晰度；这些距离尚未通过实际镜头验证。

```sh
bash tools/run_board.sh capture --load
```

程序先观察两个完整的原生752×480帧，再采集中央640×480 GRAY8帧。要求新的完成事件、S2MM已停止，随后失效CPU缓存才读DDR。采完后等待新的原生帧以覆盖FV结束和诊断更新，检查错误计数是否增加。诊断中的24MHz是硬件声明常数，不是测得的晶振频率。

4. 前两项分别通过后才合并：

```sh
bash tools/run_board.sh combined --load --seconds 10 --frame build/deploy/ui_static.rgb565
```

彩色显示每行1280字节、每帧614400字节；灰度采集每行640字节、每帧307200字节。两者使用独立物理缓冲，不能互换布局。新队列在一次使能期间只收一个完整SOF到EOF窗口，后续帧被门控；降低请求并排空后才确认可重启。GPIO状态bit4是经源域寄存器和2FF同步的rearm_ready，bit0也包含提前帧结束/重复SOF错误。S2MM改为free-run（FSYNC=0），帧起点由PL完整SOF门控保证，避免依赖后续SOF才能完成计数。诊断版本升级至0x00010003，GPIO控制4位、状态7位，不可混用旧位流和新软件。

5. 连续重复取帧及静态UI：

```sh
bash tools/run_board.sh stream --load --seconds 30 --frame build/deploy/ui_static.rgb565 --output data/private/bringup/stream
```

同一overlay、同一采集缓冲逐帧请求，DMA每帧停机后才失效缓存并复制；每帧还等原生帧计数推进，核对完整几何和坏行/坏帧无增长。错误后该会话不可重新请求。这个保守版本允许跳过传感器帧，保证软件获得完整帧，不宣称传感器满帧率无丢帧。报告accepted_copy_fps是PS取得有效整帧副本的速率，不是PCCR坐标更新率。request_to_copy不是曝光时间戳；曝光控制和硬件曝光时刻仍待补。仅保存最后一帧，循环中不压缩PNG或写图像磁盘。静态显示缓冲仍不可原地改写。

## 结果与异常

当前输出位于 `data/private/bringup/`：result.json、capture.gray8、capture.pgm、capture.png。每次覆盖当前结果，不形成一串实验版本。只在 `capture_saved_this_run=true` 时解释图像为本次结果；失败后目录可能仍留上次图像。原始数据只保存在本地，不自动上传。

图像需另行检查花屏、行偏移、全黑/全白、焦点和尺子尺寸。灰度统计不等于眼图可用，程序不将瞳孔或PCCR标记为通过。新镜头、稳定曝光和补光验证仍在后续阶段。

正常结束先保持源/接收端工作，停止两路DMA并确认都halt，再关使能并释放内存。必要时尝试VDMA软复位；复位恢复会记入结果，不能当作无故障验收。无法确认停止时，程序保留缓冲和锁并持续提示恢复，不继续分配、重载或强杀进程；完成板卡断电恢复后重新排查。软件轮询超时无法保证中断已经卡死的AXI访问。

当前自定义TMDS工程只输出视频，不发送HDMI音频。首版语音准备采用预录本地WAV，现有纽曼BS02有3.5mm AUX输入，优先有线接入；本次未发现ALSA声卡，内核未启用USB音频，优先补板载codec路径后接AUX。

寄存器/缓存依据：[AMD PG020 编程顺序](https://docs.amd.com/r/en-US/pg020_axi_vdma/Programming-Sequence)、[S2MM控制](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMACR-S2MM-VDMA-Control-Register-Offset-30h)、[S2MM状态](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMASR-S2MM-VDMA-Status-Register-Offset-34h)、[PYNQ allocate](https://pynq.readthedocs.io/en/latest/pynq_libraries/allocate.html)。


## 相机I2C与临时曝光（2026-10-20）

GPIO control bit2/3分别表示SDA/SCL拉低，0为释放，硬件从不驱动高电平；status bit5/6分别读回经2FF同步的SDA/SCL。使用模组外部3.3V上拉，不添加5V上拉。只在视频门控关闭且独占板卡时操作；Python延时控制为低速配置通路，不声称精确100kHz，不能用于逐帧曝光同步。

```bash
bash tools/run_board.sh sensor --load --output data/private/bringup/sensor
bash tools/run_board.sh capture --load --exposure-rows 120 --gain-units 16 --output data/private/bringup/exposure_short
bash tools/run_board.sh stream --load --seconds 30 --exposure-rows 240 --gain-units 32 --frame build/deploy/ui_static.rgb565 --output data/private/bringup/stream_manual
```

sensor模式仅从四个许可7位地址读取身份和寄存器，不改曝光、不运行DMA。0x48对应资料的8位写地址0x90，不能混用。实测标识0x1324与MT9V024/034系列一致，结合现有模组资料使用；单凭该ID不区分两者。

曝光和增益参数必须成对指定，当前验证范围为1–480行和16–32增益单位（16为1倍）。这是相机配置范围，绝非照眼光源参数。先保存原值，临时关闭两组AEC/AGC和HDR，保留其他位，两组设相同曝光/增益，细曝光设0；逐项写入回读，丢弃至少4个过渡帧再采集。使用完停止两路DMA后恢复原设置、回读验证、释放SDA/SCL。只要恢复失败，整次报告失败并保留原值用于诊断；不可冒称已恢复。帧率和毫秒曝光不由未经测量的时钟推算作实测值。

目前仅证明原装可见光环境的通信和控制，没有NIR补光、真实瞳孔/角膜反光或眼控精度结果。最终固定焦点景深与距离容差按docs/optics.md另行验证。

## 实时相机调焦界面（2026-10-21）

```bash
bash tools/run_board.sh preview --load --seconds 120 --output data/private/bringup/focus
bash tools/run_board.sh preview --load --seconds 60 --exposure-rows 240 --gain-units 32 --output data/private/bringup/preview
```

第一条不改传感器曝光设置；只有已确认传感器自动曝光/增益开启时才称自动曝光（本轮上一测试已恢复0xAF=3）。第二条临时手动设置并恢复。单次运行上限120秒，结束自动停机黑屏，不是产品自启程序。先看普通文字或刻度，不依赖新镜头和红外灯。侧边螺钉不应顶住调焦镜筒；旋动镜筒改变对焦位置，不改变定焦镜头的标称焦距。微调并观察清晰度，不强拧到底或触碰传感器玻璃。

显示含缩小全图、中心放大和亮度分布。放大框不是检测框，速率不是眼控坐标率。相机输入仍640×480，屏幕640×480 RGB565。使用三个显示缓冲，在空闲缓冲完成绘制/flush后请求下一个park槽，等待PARK_PTR_REG bits20:16报告硬件当前槽切换，不能把bits4:0请求回读当作已经显示。超时或指针被外部改动后禁用后续换帧；停止两路DMA后才释放所有缓冲。

中文静态标签由tools/build_preview.py生成assets/preview_template.png。板端使用像素素材和Pillow自带数字字体，无需安装或分发Windows字体。preview.png是最后一次送显RGB565的解码结果；只有本次completed/capture_saved_this_run为真时解释为本次输出。性能优化只转换变化区域，测试确认与全画布参考输出逐字节一致。

寄存器依据：[AMD PG020 Park Pointer Register](https://docs.amd.com/r/en-US/pg020_axi_vdma/PARK_PTR_REG-Park-Pointer-Register-Offset-28h)。调焦原理参考：[Commonlands M12 lens guide](https://commonlands.com/blogs/technical/what-is-an-m12-lens)，不替代本模组机械净空核验。

## 四按钮动态交互验收（2026-10-21）

确认板卡独占、屏幕HDMI OUT、SW0低档后执行：

```bash
bash tools/run_board.sh ui-test --load --output data/private/bringup/ui_interaction
```

运行固定约20秒序列，不使用--seconds、--frame或曝光参数。完全使用标明来源的程序坐标，不需观察相机、不打开采集、不播放语音。依次检查未校准、停留/防重复、丢失/有效离开、取消、暂停/恢复、断流、更多/返回、闭眼状态和停止。只有实际及时收到的样本参与停留；进程卡顿不回填过去样本，预期事件缺失会失败。

result.json含19段预期/实际事件、显示更新间隔及停机结果；interaction_trace.json在异常时也保留未完成轨迹。ui_*.png是送往显示缓冲的画面，不是对物理屏幕的摄像；必须同时参考用户屏幕观察。退出正常黑屏。2026-10-21完成18.144秒362次换帧、19.951次/秒，19段通过且用户确认无闪烁/花屏/意外黑屏。实体辅助按钮、真实校准/视线和语音未在此测试实现。

## 音频和实体辅助按键（2026-10-21）

同一Vivado工程已加入audio_aux。audio-test只做静音数字播放验收；control-test验证BTN0暂停/恢复、BTN1取消、BTN2清校准、BTN3退出。调用方法与结果边界见audio_controls.md。缺AUX线时不宣称声音已经输出到音箱。

每次Overlay.download后必须在任何DMA/自定义MMIO使用前按频率重设PL时钟0/1到50/100MHz并读回。不能仅信HWH里的频率文字：实机Linux启动PLL与Vivado默认PLL不相同，直接套HWH分频会得到31.25/62.5MHz。只设置PL时钟分频，不调用ps7_init、不改CPU/DDR PLL。改变此启动步骤后需以新位流重新回归视频，历史吞吐不据此改写。

## AUX听音（2026-10-22）

音频线连接MIC+HP至音箱AUX，先低音量。默认audio-test静音；实际听音加--audible，control-test加--audible则把程序坐标的停留事件接到本地短语。两者均为独立有界测试，不启用真实眼控。命令、按键与当前输出音量见audio_controls.md。应保存用户听感，不能仅凭DONE寄存器认定声音清楚。

## 预览原图采样（2026-10-24）

在preview模式显式加--record-preview，使用一个新的--output目录。最多12张未缩放GRAY8原图及PNG在recording/保存，逐帧均值/中心梯度写measurements.csv；采样时只拷贝到有上限的内存，双DMA确认停机后才落盘。目录已存在会在加载前拒绝，避免混入旧采样。样本时间为软件复制完成时间，不是曝光时间；中心梯度受内容、噪声、位置与曝光影响，不能判为有效眼特征或证明焦点最佳。该选项不启用语音、按钮触发或真实眼控。本地166项测试通过；板端纸张调焦120秒、灯断电单眼90秒及自然坐姿60秒已完成真实采样，各12张原图，双DMA正常停止。结果见status.md。中心黄色框仅标记放大区，不能要求实际使用者持续将眼睛对准此框；眼区跟随后续已实现，见下节。

## 眼区取景与圆点采样（2026-10-24）

preview加`--record-preview --locate-eye`启用眼区调试；需要板端已有OpenCV（已核对4.5.4），模型为assets/haarcascade_eye.xml，来源与固定哈希见eye_region_model.json，保留原始许可证。候选连续确认后跟随，当前丢失就留空；不是瞳孔、闭眼或视线判定。自然坐姿无需把眼睛对准固定中心框。

`bash tools/run_board.sh fixation --load --output data/private/bringup/新目录`为固定约60秒提示圆点采集，不加--seconds/--record-preview/--locate-eye。画面先准备6秒，再9个位置各约6秒；确认显示换帧后等待2秒，最多每位置5张原始图。双DMA停机后保存targets/manifest.json及GRAY8/PNG。样本时间是软件取帧时间，不是曝光时间；位置是提示标签，不保证实际注视、不是校准通过。无按钮/语音动作。已完成45张采样，结果见status.md。

本轮仅安装旧音频基线上的小补丁，恢复文件为板端build/recovery/eye_region_previous.zip与fixation_previous.zip。当前完整部署包使用新UART位流，不能以本轮旧位流测试声称该整包已板测。

### 室内光外观采样扩展（已完成采样，2026-10-25）

fixation加`--calibration-samples`选择约96秒的15段提示：fit_a/fit_b各五位置，最后check五位置，各最多5张原图，共75张。只采集，不建模或触发操作。tools/evaluate_appearance.py的--source指向targets目录，--output指向私有分析目录；--fresh-checks会核对config/appearance_evaluation.json固定的源码哈希，检查图绝不加入模板。新图未通过之前不能启用动作。镜头/相机位置改变必须使用新参考和新样本。


2026-10-25实测补充：`fixation --calibration-samples`已在旧音频位流完成98.197秒/1635帧/75张原图采样，双DMA正常停止；此为采样模式板测，后续本地appearance算法未部署，校准未通过，禁止将采样完成当作真实眼控通过。


新增 `fixation --appearance-check data/private/diagnostic/model.npz`：当前约43秒，先6秒准备、6秒中心参考，再五位置各6秒候选检查。中心阶段在全图重新匹配同一眼周，保留匹配强度和远端峰差拒绝；之后仍为有界局部定位。五张中心参考至少三张一致才冻结差值；不足、不一致或差异过大则拒绝。参考阶段不计分；检查目标只在预测完成后附入日志。

模型包明确diagnostic_only，训练冲突仍保留；不初始化语音/通信、不调用停留控制器、不启用校准。逐帧记录原候选及连续5帧/至少350ms稳定候选；超过250ms帧间隔或150ms处理年龄即清除。最多2000条记录及30张原图，双DMA停止后保存。已取得短时正向候选结果；实际闭眼、离框及动作仍待验证，见status.md。


### 闭眼、遮挡、离框与返回诊断

在上述命令加`--invalid-input-check`。固定92秒提示：中心参考6秒；四组各为看点6秒、按文字做动作8秒、恢复看点6秒，另有开头6秒准备。动作包括闭眼约3秒、手掌遮挡镜头约3秒、离框约3秒再回来、自然眨眼。动作期间仍用同一个冻结分类器预测，不按提示强制清空结果，不在返回时偷偷重建基准。

每个动作阶段的每次实际采集均保存320×240灰度小图（最多720张），另存每段最多5张原生640×480图。最多2400条记录；超过容量报错，不静默丢掉证据。双DMA停机后落盘。invalid_input.json中动作阶段的accepted计数包括动作前后及睁眼返回，不等于误触数；必须核对audit图像标注闭眼/遮挡/离框区间。此模式始终无按钮、语音或UART动作，报告也不自动宣称无效输入通过。冻结参数见config/invalid_input_protocol.json。

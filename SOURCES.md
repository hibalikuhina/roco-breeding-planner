# 数据来源与核对记录

核对日期：2026-10-12。

## 离线图鉴

- [洛克王国世界 WIKI 精灵图鉴](https://wiki.biligame.com/rocom/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4)：上游社区图鉴。
- [JayeGT002/rocom-wiki-data](https://github.com/JayeGT002/rocom-wiki-data)：WIKI 数据镜像及结构化 JSON；本地快照取自该项目的 [pets.json](https://jayegt002.github.io/rocom-wiki-data/data/pets.json)，仓库提交 `6ab264cb98eec1dd2dde0d7c6dfa200733a98d63`。本项目只保留查询所需字段，去除描述、图片等字段。
- [WIKI 孵蛋组别查询](https://wiki.biligame.com/rocom/%E5%AD%B5%E8%9B%8B%E7%BB%84%E5%88%AB%E6%9F%A5%E8%AF%A2)：未发现组不参与配对。

图鉴衍生数据沿用上游声明的 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.zh-hans)；请保留 WIKI 来源、上游仓库和本文件署名。游戏名称和数据版权归原权利方。本项目没有打包游戏图像或音频。

## 生蛋规则

- [WIKI 奖牌图鉴](https://wiki.biligame.com/nrc/%E5%A5%96%E7%89%8C%E5%9B%BE%E9%89%B4)：大块头/小不点与体型、婉转声/粗嗓门与声音有关；部分奖牌与地点或时间有关。
- [WIKI 精灵图鉴实例](https://wiki.biligame.com/nrc/%E5%B7%A8%E9%BC%93%E8%B1%A1)：蛋重量有明确的大小阈值，并声明仅适用于家园玩法获得的蛋。成年精灵体重不能直接套用这些阈值。
- [玩家体型讨论](https://www.taptap.cn/moment/844744598214412822?group_id=228326)：仅身高、体重显示为满值也可能没有大块头牌，说明成年体型的判牌需要谨慎估计。
- [游民星空玩家生蛋介绍](https://www.gamersky.com/handbook/202604/2116160.shtml)：蛋的物种由母方决定；亲本有异色、炫彩会提高特殊蛋机会。
- [社区繁殖介绍](https://rocokingdomworld.org/zh-hant/guides/breeding-system/)：一公一母、共享蛋组，母方定种。
- [玩家声体继承研究视频](https://www.bilibili.com/video/BV19kj36cEcx/)：可作进一步人工核查，当前未从视频提取精确公式。

## 概率处理

[游侠手游异色概率文章](https://m.ali213.net/news/gl2604/1763525.html)给出单方异色 2%–3.5% 等区间；[游侠网限定异色文章](https://gl.ali213.net/html/2026-4/1760703.html)则称单方异色约 30%–50%。这些数字相互冲突，也可能讨论不同场景。软件不默认使用任何一组。体型、声音、奖牌及炫彩的准确遗传率也未找到足够可靠的一致来源，故默认留空。

# CallTrace 上游审查

审查日期：2026-09-16。本文记录设计参考，不是依赖清单，也不表示上游为 CallTrace 背书。

CallTrace 的范围是 Python 实现的 Tree-sitter CLI，面向五种语言提供可追溯的静态调用关系。语法解析、符号解析、图遍历和输出均由程序完成，不使用 LLM 推断调用边。以下七个项目均仅借鉴概念，**无上游代码、测试、查询文件、图示或 skill 文本复用**。

## 核验方法与版本

通过官方 GitHub 仓库页面及 GitHub 连接器实际读取提交信息、固定提交下的 README、指定 skill 和许可证文件。表中的完整 SHA 来自仓库提交接口返回值，不是推测版本；审查内容链接均固定到该 SHA。提交日期为 UTC。没有安装、执行或对上游进行完整代码审计，其性能和覆盖率描述不作为 CallTrace 的验证结果。

| 项目 | 审查提交 | 提交日期 | 许可证核验结果 |
| --- | --- | --- | --- |
| [intuit/infigraph](https://github.com/intuit/infigraph) | [c54d13768b5c5ee06c8e122b60e9512351f8d8db](https://github.com/intuit/infigraph/commit/c54d13768b5c5ee06c8e122b60e9512351f8d8db) | 2026-09-13 | README 声明 Apache-2.0；LICENSE 为 Apache 2.0 标题的修改文本，GitHub 元数据为 `NOASSERTION`，不能仅凭徽章当作未经修改的标准文本 |
| [anatta-rs/ast-to-mermaid](https://github.com/anatta-rs/ast-to-mermaid) | [3362fee570b840c600adcda90ac333a2aff53a43](https://github.com/anatta-rs/ast-to-mermaid/commit/3362fee570b840c600adcda90ac333a2aff53a43) | 2026-08-09 | Apache-2.0，已读取 LICENSE |
| [scottrogowski/code2flow](https://github.com/scottrogowski/code2flow) | [c2c22afe5e12f969cc256373bf8f4eec592dc762](https://github.com/scottrogowski/code2flow/commit/c2c22afe5e12f969cc256373bf8f4eec592dc762) | 2023-01-08 | MIT，已读取 LICENSE；历史版本曾使用 LGPL |
| [senoldogann/LLM-Context-Manager](https://github.com/senoldogann/LLM-Context-Manager) | [63139e47a0394c3c445960d0fec4b3f14ebb1238](https://github.com/senoldogann/LLM-Context-Manager/commit/63139e47a0394c3c445960d0fec4b3f14ebb1238) | 2026-08-21 | MIT，已读取 LICENSE |
| [geml-spec/geml](https://github.com/geml-spec/geml) | [4f6d9b58b0424b843816979c1c4d01c290dc7d50](https://github.com/geml-spec/geml/commit/4f6d9b58b0424b843816979c1c4d01c290dc7d50) | 2026-09-15 | LICENSE 声明代码 MIT、规范文档 CC-BY-4.0；指定 skill 的归属范围未单独明确，不能笼统宣称全仓库 MIT |
| [vibeeval/vibecosystem](https://github.com/vibeeval/vibecosystem) | [3b763b1fb288f57bfa3cce76ef18184b96461a78](https://github.com/vibeeval/vibecosystem/commit/3b763b1fb288f57bfa3cce76ef18184b96461a78) | 2026-08-08 | MIT，已读取 LICENSE |
| [getappmap/appmap](https://github.com/getappmap/appmap) | [fa68b137cca857824684ccd2ac2cece38fd622d9](https://github.com/getappmap/appmap/commit/fa68b137cca857824684ccd2ac2cece38fd622d9) | 2026-07-11 | 未确认许可证：固定提交根目录无许可证文件，GitHub 仓库元数据 `license=null`；不套用同组织其它仓库的授权 |

## 逐项借鉴与限制

### 1. infigraph：先提取事实，再查询图

来源：[README](https://github.com/intuit/infigraph/blob/c54d13768b5c5ee06c8e122b60e9512351f8d8db/README.md)、[LICENSE](https://github.com/intuit/infigraph/blob/c54d13768b5c5ee06c8e122b60e9512351f8d8db/LICENSE)。

README 描述本地 AST 索引、独立符号与关系、导入感知的跨文件解析，以及正向和反向调用查询。CallTrace 借鉴解析与查询分层：先形成结构事实，再从入口遍历；调用关系与导入关系应区分。

上游同时包含图数据库、SCIP、语义搜索等更广能力。仅使用 Tree-sitter 不能自动获得编译器级类型解析。CallTrace 不继承上游语言覆盖数、性能宣传或数据库能力。许可证文本与标准文本存在差异，例如定义和再分发段落；GitHub 的 `NOASSERTION` 与 README 声明并不等价，故保留原始文件链接供核查。复用结论：仅概念，无代码复用。

### 2. ast-to-mermaid：统一中间表示与多层图

来源：[README](https://github.com/anatta-rs/ast-to-mermaid/blob/3362fee570b840c600adcda90ac333a2aff53a43/README.md)、[LICENSE](https://github.com/anatta-rs/ast-to-mermaid/blob/3362fee570b840c600adcda90ac333a2aff53a43/LICENSE)。

上游通过 Tree-sitter 构图，提供多种观察层次、JSON 元数据和 Mermaid 输出，区分未解析与外部调用。CallTrace 借鉴统一 IR 驱动导出、可选择的遍历深度、保留调用位置和解析状态。

静态源代码顺序不等于真实运行顺序。语法树必须覆盖条件表达式中的调用，不能只访问分支体；本次审查提交正是对此类遗漏的修复。CallTrace 应将递归、深度截断、未解析目标作为可见信息，而不是生成看似完整的图。没有移植 Rust 解析器、渲染器、缓存、schema 或上游测试。复用结论：仅概念，无代码复用。

### 3. code2flow：有界调用图与诚实的静态边界

来源：[README](https://github.com/scottrogowski/code2flow/blob/c2c22afe5e12f969cc256373bf8f4eec592dc762/README.md)、[LICENSE](https://github.com/scottrogowski/code2flow/blob/c2c22afe5e12f969cc256373bf8f4eec592dc762/LICENSE)。

上游采用提取定义、查找调用、作用域匹配、连接节点的流程，并允许从函数限制上下游深度。CallTrace 借鉴入口聚焦和有界遍历；候选名称不足以证明调用目标。

README 明确列出动态语言、重名、外部导入、匿名函数及别名的限制。CallTrace 不采用“全项目同名只有一个就必然命中”的强断言，无法确定的调用必须保留未解析记录。README 说明 2021 年重写前存在 LGPL 历史，本审查 MIT 结论只对应表内版本。复用结论：仅概念，无代码复用。

### 4. LLM-Context-Manager：双阶段索引与证据定位

来源：[README](https://github.com/senoldogann/LLM-Context-Manager/blob/63139e47a0394c3c445960d0fec4b3f14ebb1238/README.md)、[LICENSE](https://github.com/senoldogann/LLM-Context-Manager/blob/63139e47a0394c3c445960d0fec4b3f14ebb1238/LICENSE)。

README 将结构图、向量检索和解析器分开，描述双阶段索引、稳定节点定位、调用链遍历以及结果置信度。CallTrace 借鉴先收集符号再解析调用的阶段划分，并为关系携带源位置与解析依据。

结构关系和语义相似度不能混为一谈。CallTrace 不运行 embedding 服务，不引入向量数据库，也不把检索分数转换成确定调用边。上游检索基准不是本项目精确率证明。复用结论：仅概念，无代码复用。

### 5. GEML code-graph skill：候选、盲区与证据导航

来源：[Source project](https://github.com/geml-spec/geml/tree/4f6d9b58b0424b843816979c1c4d01c290dc7d50)、[LICENSE](https://github.com/geml-spec/geml/blob/4f6d9b58b0424b843816979c1c4d01c290dc7d50/LICENSE)。

该 skill 以符号定位、容器概览、正反向关系与源码位置组织导航，明确区分候选集合、低置信度与未解析调用。CallTrace 借鉴“先定位，再追踪，再查看证据”的使用顺序，以及缺少已解析调用不能证明没有调用这一表达原则。

上游依赖 SCIP、Joern 等不同精度的索引器，并明确列出部分间接调用缺口。CallTrace 的 Tree-sitter 分析不声称具备同等解析精度。LICENSE 引用的根目录 `LICENSE-spec.md` 在本次固定版本读取返回 404，因此这里只记录主 LICENSE 的分区声明，不补造缺失授权文本；skill 的授权范围不作扩张解释。没有复制该 skill、GEML 格式、命令流程或适配器。复用结论：仅概念，无代码复用。

### 6. vibecosystem explore skill：明确探索范围与深度

来源：[Source project](https://github.com/vibeeval/vibecosystem/tree/3b763b1fb288f57bfa3cce76ef18184b96461a78)、[LICENSE](https://github.com/vibeeval/vibecosystem/blob/3b763b1fb288f57bfa3cce76ef18184b96461a78/LICENSE)。

该 skill 将探索按概览、深入研究、架构分析分组，并围绕范围、入口和交接产物组织工作。CallTrace 借鉴入口、方向、深度与输出格式显式化，使同一份结构数据可以服务不同问题。

探索任务的“深度”与调用图的数值 hop 深度是不同概念，应分别解释。上游是代理工作流，依赖其它工具和 skill；CallTrace 的确定性 CLI 不依赖这些工作流，不以代理的架构判断补充调用事实。复用结论：仅概念，无代码或 skill 文本复用。

### 7. AppMap：结构实体与动态事件的区别

来源：[格式规范 README](https://github.com/getappmap/appmap/blob/fa68b137cca857824684ccd2ac2cece38fd622d9/README.md)、[固定提交根目录](https://github.com/getappmap/appmap/tree/fa68b137cca857824684ccd2ac2cece38fd622d9)。

指定仓库是 AppMap 数据规范，描述结构实体、执行事件和源位置的关联。CallTrace 借鉴证据可回到源码、数据应有明确格式版本的原则；统一 IR 采用本项目自己的定义。

AppMap 的事件来自程序执行，CallTrace 的边来自静态分析，二者不能当作相同证据。CallTrace 不生成伪造的运行事件、耗时、参数值或线程信息，也不声称输出兼容 AppMap。根目录仅含 `.github`、`README.md`、`sequence.json.md`；常见许可证路径读取均返回 404，尚未确认本仓库的再分发授权。复用结论：仅概念，无代码、schema 或规范正文复用。

## 对 CallTrace 的设计约束

以下为本项目根据审查作出的设计选择，不代表上游承诺或已完成的测试报告。

1. **确定性解析**：语法事实由 Tree-sitter 提取，解析规则可检查；LLM 可以解释输出，不能添加推测调用边。
2. **可追溯证据**：符号保留文件与位置，边保留调用位置和解析状态；重名与动态目标不得静默选取任意候选。
3. **统一 IR**：语言适配与输出分离，JSON 与图输出基于同一组事实；显示标签不充当全局符号标识。
4. **有界深度**：数值深度表示入口到节点的调用边数；递归终止、外部边界和截断需要明确表达。
5. **静态能力边界**：完整语法解析不等于完整类型推断；无已解析边不等于无调用；静态路径不等于已执行路径。
6. **独立 skill**：本项目使用说明应围绕自己的 CLI、证据和局限编写，不复制上游提示词，也不依赖模型生成图结构。

## 授权与复用登记

七项目的复用方式均为“概念参考”，复用文件数为 0，移植代码行数为 0。CallTrace 自有代码采用根目录 [MIT LICENSE](../LICENSE)，其中的版权声明不覆盖任何第三方组件。

Tree-sitter 及语言 grammar 等实际运行依赖需要按其各自许可证使用；它们不属于本表七项设计参考的代码复用范围。如果未来引入任何上游代码、查询、测试或文字，应新增具体路径、固定版本、修改说明和所需许可证/署名记录，而不能继续沿用本文的零复用声明。

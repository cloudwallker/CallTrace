# CallTrace

**中文简介：** 从指定源码函数静态生成带源码位置的 Mermaid 时序图，保留控制流及无法解析的调用目标。

**English overview:** Generate Mermaid sequence diagrams from a selected source function, with source locations, control flow, and explicit unresolved calls.

## 使用 / Usage

Python 3.11+；支持 Python、JavaScript、TypeScript、Java 和 Go。分析目标项目时不执行其代码。

Python 3.11+; supports Python, JavaScript, TypeScript, Java, and Go. Target projects are analyzed without executing their code.

```text
python -m pip install -e .
calltrace --help
```

## 许可 / License

见 [LICENSE](LICENSE)。 / See [LICENSE](LICENSE).

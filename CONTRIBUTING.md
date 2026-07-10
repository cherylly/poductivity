# 开发指南 (Contributing Guide)

感谢您对本项目的关注！本文档介绍如何参与项目开发。

---

## 开发环境设置

### 系统要求

- 现代浏览器（Chrome、Firefox、Safari、Edge）
- 文本编辑器（推荐 VS Code）
- 本地 HTTP 服务器（可选）

### 快速开始

1. **克隆项目**
   ```bash
   git clone <项目地址>
   cd claude
   ```

2. **本地预览**
   - 直接双击 `forbes-billionaires.html` 在浏览器中打开
   - 或使用本地服务器：
     ```bash
     # Python 3
     python -m http.server 8000

     # Node.js
     npx serve .
     ```

3. **访问页面**
   - 浏览器打开 `http://localhost:8000/forbes-billionaires.html`

---

## 项目结构

```
claude/
├── forbes-billionaires.html   # 主页面文件
├── README.md                  # 项目说明
├── CHANGELOG.md               # 更新日志
└── CONTRIBUTING.md            # 本文档
```

---

## 代码规范

### HTML 规范

- 使用语义化 HTML5 标签
- 保持良好的缩进（2空格或4空格）
- 添加适当的注释

### CSS 规范

- 使用 BEM 或类似命名规范
- 避免过度嵌套
- 响应式设计优先

---

## 如何贡献

### 报告问题

- 描述问题的具体表现
- 提供复现步骤
- 说明浏览器和操作系统版本

### 提交代码

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/新功能`)
3. 提交更改 (`git commit -m '添加新功能'`)
4. 推送到分支 (`git push origin feature/新功能`)
5. 创建 Pull Request

---

## 联系方式

如有问题，请通过项目 Issues 联系。
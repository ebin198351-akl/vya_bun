# 邮件发送设置说明 / Email Setup Instructions

## 中文说明

### 1. 创建 Gmail 应用密码

由于 Gmail 的安全设置，需要使用"应用密码"而不是普通密码：

1. 访问 [Google 账户设置](https://myaccount.google.com/)
2. 进入 **安全性** > **两步验证**（如果还没开启，需要先开启）
3. 滚动到底部，找到 **应用密码**
4. 选择应用：**邮件**，设备：**其他（自定义名称）**，输入 "Vya's Kitchen"
5. 点击 **生成**
6. 复制生成的 16 位密码

### 2. 配置环境变量（可选）

代码中已经配置了默认邮箱和密码，如果需要修改，可以：

1. 创建 `.env` 文件（可选）
2. 编辑 `.env` 文件，填入你的信息：
   ```
   GMAIL_USER=vya2025.kitchen@gmail.com
   GMAIL_APP_PASSWORD=Ebin@2021
   ```

**注意**：如果直接使用普通密码可能无法工作，Gmail 通常需要应用密码。如果遇到认证错误，请按照步骤 1 创建应用密码。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行服务器

```bash
python server.py
```

现在联系表单会直接将邮件发送到你的 Gmail 邮箱！

---

## English Instructions

### 1. Create Gmail App Password

Due to Gmail security settings, you need to use an "App Password" instead of your regular password:

1. Go to [Google Account settings](https://myaccount.google.com/)
2. Navigate to **Security** > **2-Step Verification** (enable if not already enabled)
3. Scroll down to **App passwords**
4. Select app: **Mail**, device: **Other (Custom name)**, enter "Vya's Kitchen"
5. Click **Generate**
6. Copy the generated 16-character password

### 2. Configure Environment Variables

1. Copy `.env.example` to `.env`
2. Edit `.env` file with your information:
   ```
   GMAIL_USER=yawen4092@gmail.com
   GMAIL_APP_PASSWORD=your_16_character_app_password
   ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run Server

```bash
python server.py
```

Now the contact form will send emails directly to your Gmail inbox!


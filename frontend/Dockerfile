# 使用 Node 20 基础镜像
FROM node:20-slim

WORKDIR /app

# 先拷贝 package.json 以利用 Docker 缓存层
COPY package*.json ./

# 安装依赖
RUN npm install

# 拷贝其余源码
COPY . .

# Vite 默认端口是 5173
EXPOSE 5173

# --host 必须加上，否则 Docker 外部无法访问容器内的 Vite
CMD ["npm", "run", "dev", "--", "--host"]

RUN npm install react-markdown
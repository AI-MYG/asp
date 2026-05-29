# Surface Conventions

## 元数据

- **类型**: Reference
- **适用场景**: 各 surface 的构建、部署、分支约定汇总

## Backend (asp-backend)

- **语言/框架**: Python, FastAPI
- **Base branch**: `dev`
- **部署**: CVM-1 Docker container (`inputbaby-backend`)
- **构建**: `docker build` → `docker compose up`
- **测试**: `pytest` (容器内执行)
- **本地路径**: `projects/asp/backend`

## App (asp-app)

- **语言/框架**: Flutter, Dart
- **Base branch**: `main`
- **部署**: App Store (iOS) / APK 分发 (Android)
- **构建**: `flutter build apk` / `flutter build ios`
- **测试**: `flutter test`
- **本地路径**: `projects/asp/app`

## Admin (asp-admin)

- **语言/框架**: Vue.js
- **Base branch**: `main`
- **部署**: CVM-1 Nginx (`/var/www/admin`)
- **构建**: `npm run build`
- **测试**: `npm test`
- **本地路径**: `projects/asp/admin`

## WeCom (asp-wecom)

- **语言/框架**: JavaScript, WeCom SDK
- **Base branch**: `main`
- **部署**: CVM-1
- **本地路径**: `projects/asp/wecom`

## Websites (asp-websites)

- **语言/框架**: HTML, CSS, JavaScript
- **Base branch**: `main`
- **部署**: COS 静态托管 + CVM 下载页
- **本地路径**: `projects/asp/websites`

## Canonical (asp-canonical)

- **内容**: 课程数据、配置、映射表
- **Base branch**: `main`
- **部署**: 无独立部署，被 backend 引用
- **本地路径**: `projects/asp/canonical`

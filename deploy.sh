#!/bin/bash

# Project Claw 部署脚本
# 支持本地运行和 Docker 部署

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印函数
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查环境
check_environment() {
    print_info "检查环境..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安装"
        exit 1
    fi
    
    print_info "Python3 版本: $(python3 --version)"
}

# 安装依赖
install_dependencies() {
    print_info "安装依赖..."
    
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt 不存在"
        exit 1
    fi
    
    pip install -r requirements.txt
    print_info "依赖安装完成"
}

# 配置环境变量
setup_env() {
    print_info "配置环境变量..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_warn "已创建 .env 文件，请编辑并填入实际值"
        else
            print_error ".env.example 不存在"
            exit 1
        fi
    fi
    
    # 加载环境变量
    export $(cat .env | grep -v '#' | xargs)
}

# 本地运行
run_local() {
    print_info "本地运行 Project Claw..."
    
    check_environment
    install_dependencies
    setup_env
    
    print_info "启动系统..."
    python3 lobster_with_openclaw.py
}

# Docker 构建
build_docker() {
    print_info "构建 Docker 镜像..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        exit 1
    fi
    
    docker build -t project-claw:latest .
    print_info "Docker 镜像构建完成"
}

# Docker 运行
run_docker() {
    print_info "使用 Docker 运行 Project Claw..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        exit 1
    fi
    
    setup_env
    
    docker run -it \
        --name project-claw \
        -p 8000:8000 \
        -e DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY} \
        -e FEISHU_APP_ID=${FEISHU_APP_ID} \
        -e FEISHU_APP_SECRET=${FEISHU_APP_SECRET} \
        -v $(pwd)/logs:/app/logs \
        project-claw:latest
}

# Docker Compose 运行
run_docker_compose() {
    print_info "使用 Docker Compose 运行 Project Claw..."
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose 未安装"
        exit 1
    fi
    
    setup_env
    
    docker-compose up -d
    print_info "Docker Compose 启动完成"
    print_info "查看日志: docker-compose logs -f"
}

# 停止 Docker Compose
stop_docker_compose() {
    print_info "停止 Docker Compose..."
    
    docker-compose down
    print_info "Docker Compose 已停止"
}

# 显示帮助
show_help() {
    cat << EOF
Project Claw 部署脚本

用法: ./deploy.sh [命令]

命令:
    local           本地运行（推荐开发环境）
    docker-build    构建 Docker 镜像
    docker-run      使用 Docker 运行
    docker-compose  使用 Docker Compose 运行（推荐生产环境）
    docker-stop     停止 Docker Compose
    help            显示此帮助信息

示例:
    ./deploy.sh local
    ./deploy.sh docker-compose
    ./deploy.sh docker-stop

EOF
}

# 主函数
main() {
    case "${1:-help}" in
        local)
            run_local
            ;;
        docker-build)
            build_docker
            ;;
        docker-run)
            run_docker
            ;;
        docker-compose)
            run_docker_compose
            ;;
        docker-stop)
            stop_docker_compose
            ;;
        help)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"

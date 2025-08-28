#!/bin/bash
###############################################################################
# Usage examples:
# --------------
# 1. Build an image with default options:
# $ ./docker/plantimager/webui/build.sh
#
# 2. Build an image with a 'debug' tag:
# $ ./docker/plantimager/webui/build.sh -t debug
###############################################################################

# --------------------------------
# Functions for colors and messages
# --------------------------------
setup_colors() {
  RED="\033[0;31m"    # Define red color code
  GREEN="\033[0;32m"  # Define green color code
  YELLOW="\033[0;33m" # Define yellow color code
  BLUE="\033[0;34m"   # Define blue color code for debug messages
  NC="\033[0m"        # No Color code to reset colors
  INFO="${GREEN}INFO${NC}    "    # Prefix for info messages
  WARNING="${YELLOW}WARNING${NC} " # Prefix for warning messages
  ERROR="${RED}$(bold ERROR)${NC}   " # Prefix for error messages using bold function
  DEBUG="${BLUE}DEBUG${NC}   "   # Prefix for debug messages
}

bold() {
  echo -e "\e[1m$*\e[0m" # Make text bold and reset
}

log_info() {
  echo -e "${INFO}$1" # Print info message with INFO prefix
}

log_warning() {
  echo -e "${WARNING}$1" # Print warning message with WARNING prefix
}

log_error() {
  echo -e "${ERROR}$1" # Print error message with ERROR prefix
}

log_debug() {
  if [ "${DEBUG_MODE}" = true ]; then
    echo -e "${DEBUG}$1" # Print debug message with DEBUG prefix if debug mode is enabled
  fi
}
# --------------------------------
# Functions for script initialization
# --------------------------------
initialize_variables() {
  # Image tag to use, 'latest' by default:
  VTAG="latest"
  # String aggregating the docker build options to use:
  DOCKER_OPTS=""
  # Debug mode is disabled by default
  DEBUG_MODE=false
}

# --------------------------------
# Check for required dependencies
# --------------------------------
check_dependencies() {
  if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker is not installed or not found!"
    exit 1
  fi
}

# --------------------------------
# Usage information function
# --------------------------------
show_usage() {
  echo -e "$(bold USAGE):"
  echo "  ./docker/webui/build.sh [OPTIONS]"
  echo ""

  echo -e "$(bold DESCRIPTION):"
  echo "  Build a docker image named 'roboticsmicrofarms/plantimager_webui' using 'Dockerfile' in 'docker/webui/'.

  Must be run from the 'plant-imager' repository root folder as it will be copied during at image build time.
  Do not forget to initialize or update the sub-modules if necessary!"
  echo ""

  echo -e "$(bold OPTIONS):"
  echo "  -t, --tag
    Image tag to use." \
    "By default, use the '${VTAG}' tag."
  # -- Docker options:
  echo "  --no-cache
    Do not use cache when building the image, (re)start from scratch."
  echo "  --pull
    Always attempt to pull a newer version of the parent image."
  echo "  --plain
    Plain output during docker build."
  # -- Debug option:
  echo "  --debug
    Enable debug mode to print additional debug information."
  # -- General options:
  echo "  -h, --help
    Output a usage message and exit."
}

# --------------------------------
# Command line parsing function
# --------------------------------
parse_arguments() {
  while [ "$1" != "" ]; do
    case $1 in
    -t | --tag)
      shift
      VTAG=$1
      ;;
    --no-cache)
      DOCKER_OPTS="${DOCKER_OPTS} --no-cache"
      ;;
    --pull)
      DOCKER_OPTS="${DOCKER_OPTS} --pull"
      ;;
    --plain)
      DOCKER_OPTS="${DOCKER_OPTS} --progress=plain"
      ;;
    --debug)
      DEBUG_MODE=true
      log_debug "Debug mode enabled"
      ;;
    -h | --help)
      show_usage
      exit 0
      ;;
    *)
      show_usage
      exit 1
      ;;
    esac
    shift
  done
}

# --------------------------------
# Build Docker image
# --------------------------------
build_docker_image() {
  docker_cmd="docker build"
  docker_cmd+=" -t roboticsmicrofarms/plantimager_webui:${VTAG}"
  docker_cmd+=" ${DOCKER_OPTS}"
  docker_cmd+=" -f docker/webui/Dockerfile ."

  # Print the build configuration options
  log_debug "Build configuration:"
  log_debug "- Docker tag: ${VTAG}"
  log_debug "- Docker options: ${DOCKER_OPTS}"
  # Print the full command that will be executed
  log_debug "Executing command: ${docker_cmd}"

  # Track start time for build process
  start_time=$(date +%s)

  # Execute the docker build command
  eval ${docker_cmd}
  docker_build_status=$?

  elapsed_time=$(($(date +%s) - start_time))
  if [ ${docker_build_status} -eq 0 ]; then
    log_info "Docker build SUCCEEDED in ${elapsed_time}s!"
  else
    log_error "Docker build FAILED after ${elapsed_time}s with code ${docker_build_status}!"
  fi

  exit ${docker_build_status}
}

# --------------------------------
# Main script execution
# --------------------------------
main() {
  setup_colors
  check_dependencies
  initialize_variables
  parse_arguments "$@"
  build_docker_image
}

# Execute main function with all arguments
main "$@"

# Compact dispatcher for AutoScribe managed-vault lifecycle helpers.

cli() {
  local command="$1"
  shift 2>/dev/null || true

  case "$command" in
    create-vault) create-vault "$@" ;;
    update-vault) update-vault "$@" ;;
    update-core) update-core "$@" ;;
    ''|-h|--help|help)
      print 'usage: cli {create-vault|update-vault|update-core} [args...]'
      ;;
    *)
      print -u2 -- "unknown AutoScribe client command: $command"
      return 64
      ;;
  esac
}

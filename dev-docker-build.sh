#!/bin/bash
# File: deploy-complex-push.sh
# Description: Rebuilds local Docker env, commits changes (Commit A).
#              Pushes Commit A to origin.
#              Creates temporary commit (Commit B) with root Dockerfile.
#              Pushes Commit B to space.
#              Resets local branch back to Commit A and cleans up.

# --- Konfigurasi ---
set -e # Keluar segera jika sebuah perintah keluar dengan status bukan nol

# File Compose untuk build/run lokal
COMPOSE_FILE="docker-compose.dev.yml"

# Nama Remote Git
REMOTE_DEV="origin"
REMOTE_SPACE="space"

# Path Dockerfile Sumber
SOURCE_DOCKERFILE_PATH="docker/Dockerfile"
# Path Dockerfile Target Sementara (Root)
TEMP_ROOT_DOCKERFILE="Dockerfile"

# Konfigurasi Umum
GIT_BRANCH="main"
WAIT_SECONDS=10
LOG_TAIL_LINES=50

# Pesan Commit Sementara
TEMP_COMMIT_MSG="Temporary commit: Add root Dockerfile for space deployment"

# --- Variabel Internal ---
STEP_COUNT=0
ROOT_DOCKERFILE_CLEANUP_NEEDED=false # Flag untuk cleanup

# --- Fungsi Bantuan ---
log_step() {
    STEP_COUNT=$((STEP_COUNT + 1))
    local phase_marker="$1"
    local message="$2"
    echo -e "\n[STEP ${STEP_COUNT} | ${phase_marker}] ${message}"
}

run_command() {
    echo "   🚀 Executing: $@"
    "$@"
    local status=$?
    if [ $status -ne 0 ]; then
        echo "   ❌ ERROR: Command failed with status $status: $*" >&2
        # Mencoba reset jika error terjadi setelah commit sementara dibuat
        # Ini mungkin tidak selalu aman, tergantung di mana error terjadi
        # cleanup_local_state # Pertimbangkan fungsi cleanup yang lebih canggih jika perlu
        exit $status
    fi
    echo "   ✅ Command successful: $*"
}

# Fungsi check_container_exec dan check_local_containers (sama seperti sebelumnya)
check_container_exec() {
    local full_container_name=$1; local compose_file_ref=$2
    echo "   🔍 Checking accessibility for container [${compose_file_ref}]: ${full_container_name}...";
    if docker exec "${full_container_name}" sh -c "exit 0" > /dev/null 2>&1; then echo "   ✅ Container ${full_container_name} is accessible."; return 0;
    else if docker ps --filter "name=^/${full_container_name}$" --filter "status=running" --quiet > /dev/null; then echo "   ⚠️ Container ${full_container_name} is RUNNING but not accessible via 'docker exec'. Might still be initializing."; return 1;
         else echo "   ❌ Container ${full_container_name} is NOT RUNNING or not found."; return 1; fi; fi
}
check_local_containers() {
    local compose_file=$1; log_step "LOCAL" "Checking local container status and accessibility for ${compose_file}..."; local services; services=$(docker compose -f "${compose_file}" config --services); local accessible_services=(); local inaccessible_services=(); local project_name; project_name=$(docker compose -f "${compose_file}" config --format json | grep '"name":' | sed 's/.*"name": "\(.*\)",/\1/' || echo "localproject");
    for service in $services; do local container_name_guess="${project_name}-${service}-1"; local container_id; container_id=$(docker ps -q --filter "label=com.docker.compose.service=${service}" --filter "label=com.docker.compose.project=${project_name}"); local actual_container_name="";
        if [ -n "$container_id" ]; then actual_container_name=$(docker inspect --format '{{.Name}}' $container_id | sed 's/^\///'); else if docker ps --filter "name=^/${container_name_guess}$" --filter "status=running" --quiet > /dev/null; then actual_container_name="${container_name_guess}"; else echo "   ❌ Could not find a running local container for service '${service}' [${compose_file}]."; inaccessible_services+=("${service} (Container not found)"); continue; fi; fi
        if check_container_exec "${actual_container_name}" "$(basename "${compose_file}")"; then accessible_services+=("${service} (${actual_container_name})"); else inaccessible_services+=("${service} (${actual_container_name})"); fi; done
    echo ""; echo "   --- Local Accessibility Summary ---"; if [ ${#accessible_services[@]} -gt 0 ]; then echo "   ✅ Accessible Services:"; for svc in "${accessible_services[@]}"; do echo "      - $svc"; done; else echo "   ℹ️ No local services confirmed accessible."; fi; if [ ${#inaccessible_services[@]} -gt 0 ]; then echo "   ❌ Inaccessible/Problematic Services:"; for svc in "${inaccessible_services[@]}"; do echo "      - $svc"; done; else echo "   ℹ️ All checked local services seem accessible or running."; fi; echo "   ----------------------------------"
}


# Fungsi commit utama (Commit A)
commit_main_changes() {
    log_step "GIT" "Checking for main Git changes..."
    # Periksa perubahan pada file terlacak, abaikan file tak terlacak (seperti Dockerfile root jika belum di-add)
    if [[ -z $(git status --porcelain=v1 --untracked-files=no) ]]; then
        echo "   ℹ️ No tracked changes detected in the working directory. Skipping main commit."
        return 1 # Mengembalikan status 1 untuk menandakan tidak ada commit
    fi
    echo "   📝 Staging all tracked changes for main commit..."
    run_command git add -u # Hanya stage file terlacak yang berubah/dihapus
    # Pertimbangkan 'git add .' jika Anda juga ingin menambahkan file BARU yang TIDAK diabaikan
    local commit_message="Automated commit after local build on $(date +'%Y-%m-%d %H:%M:%S %Z')"
    echo "   📝 Creating main commit (Commit A) with message: '${commit_message}'"
    run_command git commit -m "$commit_message"
    return 0 # Sukses, commit dibuat
}

ensure_gitignore_entry() {
    local entry="$1"; local gitignore_file=".gitignore"; if [ ! -f "$gitignore_file" ]; then touch "$gitignore_file"; fi
    if ! grep -qxF "$entry" "$gitignore_file"; then echo "   ➕ Adding '${entry}' to ${gitignore_file}..."; if [ -s "$gitignore_file" ]; then echo "" >> "$gitignore_file"; fi; echo "$entry" >> "$gitignore_file"; echo "   ✅ Entry '${entry}' added."; fi
}

# Fungsi cleanup - menghapus Dockerfile root jika flag diset
cleanup_root_dockerfile() {
  if [ "$ROOT_DOCKERFILE_CLEANUP_NEEDED" = true ] && [ -f "$TEMP_ROOT_DOCKERFILE" ]; then
    echo "   🧹 Cleaning up temporary root Dockerfile (${TEMP_ROOT_DOCKERFILE})..."
    rm -f "$TEMP_ROOT_DOCKERFILE"
    ROOT_DOCKERFILE_CLEANUP_NEEDED=false # Reset flag
  fi
}

# --- Awal Eksekusi Skrip ---

echo "🚀 Starting Complex Deployment Process (Local Build -> Commit A -> Push Origin -> Temp Commit B -> Push Space -> Reset Local)..."
echo "-------------------------------------------"

# Pasang trap untuk mencoba cleanup jika skrip keluar tak terduga
trap cleanup_root_dockerfile EXIT SIGINT SIGTERM

# Langkah 0: Pastikan Dockerfile root ada di .gitignore
log_step "PREP" "Ensuring root Dockerfile ('${TEMP_ROOT_DOCKERFILE}') is in .gitignore"
ensure_gitignore_entry "${TEMP_ROOT_DOCKERFILE}"

# Validasi file
log_step "PREP" "Validating required files..."
if [ ! -f "${SOURCE_DOCKERFILE_PATH}" ]; then echo "❌ ERROR: Source Dockerfile '${SOURCE_DOCKERFILE_PATH}' not found!"; exit 1; fi
if [ ! -f "${COMPOSE_FILE}" ]; then echo "❌ ERROR: Compose file '${COMPOSE_FILE}' not found!"; exit 1; fi
echo "   ✅ Required files seem present."
echo "-------------------------------------------"

# === FASE 1: LOCAL DOCKER COMPOSE ===
log_step "LOCAL" "Stopping existing local containers (using ${COMPOSE_FILE})..."
docker compose -f "${COMPOSE_FILE}" down --remove-orphans --volumes || true
log_step "LOCAL" "Rebuilding and starting local containers (using ${COMPOSE_FILE})..."
run_command docker compose -f "${COMPOSE_FILE}" up --build -d --remove-orphans
log_step "LOCAL" "Waiting ${WAIT_SECONDS}s for local containers..."
sleep "${WAIT_SECONDS}"
check_local_containers "${COMPOSE_FILE}"
log_step "LOCAL" "Showing last ${LOG_TAIL_LINES} lines of local logs..."
run_command docker compose -f "${COMPOSE_FILE}" logs --tail="${LOG_TAIL_LINES}" --no-log-prefix
echo "-------------------------------------------"
echo "✅ LOCAL Phase Complete."
echo "-------------------------------------------"

# === FASE 2: GIT - Commit A & Push Origin ===
# Simpan commit hash sebelum potensi commit baru
HEAD_BEFORE_MAIN_COMMIT=$(git rev-parse HEAD)

commit_main_changes # Coba buat Commit A
main_commit_status=$?

if [ $main_commit_status -eq 0 ]; then
    # Commit A dibuat
    COMMIT_A_HASH=$(git rev-parse HEAD)
    log_step "GIT" "Pushing main commit (Commit A: ${COMMIT_A_HASH:0:7}) to ${REMOTE_DEV}..."
    run_command git push "${REMOTE_DEV}" "${GIT_BRANCH}"
else
    # Tidak ada perubahan untuk Commit A
    COMMIT_A_HASH=$HEAD_BEFORE_MAIN_COMMIT
    log_step "GIT" "No changes detected for main commit. Using current HEAD (${COMMIT_A_HASH:0:7}) as base for space push."
fi
echo "-------------------------------------------"
echo "✅ GIT Phase 1 (Commit A / Push Origin) Complete. Base commit: ${COMMIT_A_HASH:0:7}"
echo "-------------------------------------------"

# === FASE 3: GIT - Prepare & Push Space (Commit B) ===
log_step "SPACE PREP" "Preparing temporary commit (Commit B) for Space push..."

# Pastikan kita berada pada Commit A
if [ "$(git rev-parse HEAD)" != "$COMMIT_A_HASH" ]; then
    echo "❌ ERROR: HEAD is not at the expected Commit A (${COMMIT_A_HASH:0:7}). Aborting."
    exit 1
fi

# Pastikan working directory bersih relatif terhadap Commit A
if ! git diff --quiet HEAD; then
   echo "   ⚠️ Warning: Working directory has uncommitted changes relative to Commit A. These changes will NOT be included in the push to space."
   # Anda bisa memilih untuk exit di sini jika ini tidak diinginkan:
   # echo "❌ ERROR: Working directory not clean relative to Commit A. Please commit or stash changes."
   # exit 1
fi

# Salin Dockerfile dari sumber ke root
echo "   Copying '${SOURCE_DOCKERFILE_PATH}' -> '${TEMP_ROOT_DOCKERFILE}'"
run_command cp "${SOURCE_DOCKERFILE_PATH}" "${TEMP_ROOT_DOCKERFILE}"
ROOT_DOCKERFILE_CLEANUP_NEEDED=true # Set flag untuk cleanup

# Tambahkan Dockerfile root ke index
echo "   Staging temporary root Dockerfile..."
run_command git add "${TEMP_ROOT_DOCKERFILE}"

# Buat commit sementara (Commit B)
echo "   Creating temporary commit (Commit B)..."
# Gunakan --no-verify untuk melewati hook pre-commit jika ada
run_command git commit --no-verify -m "${TEMP_COMMIT_MSG}"
COMMIT_B_HASH=$(git rev-parse HEAD)
echo "   ✅ Temporary Commit B created: ${COMMIT_B_HASH:0:7}"

log_step "SPACE PUSH" "Pushing temporary commit (Commit B: ${COMMIT_B_HASH:0:7}) to ${REMOTE_SPACE}..."
echo "   ⚠️ This push uses --force-with-lease, overwriting '${GIT_BRANCH}' on '${REMOTE_SPACE}'."
# Push Commit B (HEAD saat ini) ke branch tujuan di remote space
# --force-with-lease lebih aman, hanya akan push jika remote belum berubah sejak fetch terakhir
run_command git push --force-with-lease "${REMOTE_SPACE}" "HEAD:${GIT_BRANCH}"

echo "-------------------------------------------"
echo "✅ SPACE Push (Commit B) Complete."
echo "-------------------------------------------"


# === FASE 4: GIT - Cleanup Local State ===
log_step "CLEANUP" "Resetting local '${GIT_BRANCH}' branch back to Commit A (${COMMIT_A_HASH:0:7})..."
echo "   Current HEAD is Commit B: $(git rev-parse HEAD | cut -c1-7)"
# Reset --hard akan menghapus Commit B dari riwayat lokal dan membersihkan working directory
# termasuk menghapus TEMP_ROOT_DOCKERFILE karena sudah di-'add' sebelum Commit B
run_command git reset --hard "${COMMIT_A_HASH}"
echo "   ✅ Local branch reset to Commit A."

# Hapus file sementara secara eksplisit (sebagai jaring pengaman tambahan, meskipun reset --hard harusnya sudah menghapusnya)
cleanup_root_dockerfile

echo "-------------------------------------------"
echo "✅ Local Cleanup Complete."
echo "-------------------------------------------"


log_step "ALL" "Complex deployment script finished successfully!"
echo "✅ Orchestration complete. Origin has Commit A, Space has Commit B (incl. root Dockerfile). Local repo reset to Commit A."
exit 0
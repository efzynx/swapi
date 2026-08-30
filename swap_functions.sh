#!/usr/bin/env bash
# ==============================================================================
# swapi - Modular Bash Swap Management Functions
# ==============================================================================
# Menyediakan fungsi modular untuk:
# 1. Format partisi swap dengan preservasi UUID & cek resume GRUB
# 2. Pembuatan swapfile kompatibel Btrfs (NoCoW/NoCompression) & Standar
# 3. Sanitasi, backup, dan pencegahan duplikasi entri di /etc/fstab
# ==============================================================================

# ---------------------------------------------------------
# Logging Helpers
# ---------------------------------------------------------
log_info() {
    echo -e "\e[34m[INFO]\e[0m $1"
}

log_success() {
    echo -e "\e[32m[SUCCESS]\e[0m $1"
}

log_warning() {
    echo -e "\e[33m[WARNING]\e[0m $1"
}

log_error() {
    echo -e "\e[31m[ERROR]\e[0m $1" >&2
}

# ---------------------------------------------------------
# Validasi Hak Akses (Root / Sudo)
# ---------------------------------------------------------
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Fungsi ini membutuhkan hak akses root / sudo."
        return 1
    fi
    return 0
}

# ---------------------------------------------------------
# 1. Penanganan UUID Partisi Swap
# ---------------------------------------------------------
get_partition_uuid() {
    local dev="$1"
    local uuid=""

    if command -v blkid &>/dev/null; then
        uuid=$(blkid -s UUID -o value "$dev" 2>/dev/null)
    fi

    if [[ -z "$uuid" ]] && command -v lsblk &>/dev/null; then
        uuid=$(lsblk -no UUID "$dev" 2>/dev/null | head -n 1)
    fi

    echo "$uuid"
}

check_grub_resume() {
    local new_uuid="$1"
    local grub_file="/etc/default/grub"

    if [[ -f "$grub_file" ]] && grep -q "resume=" "$grub_file"; then
        log_warning "Parameter 'resume=' ditemukan pada $grub_file!"
        log_warning "Jika partisi ini digunakan untuk hibernasi (resume), pastikan parameter diperbarui ke: resume=UUID=$new_uuid"
        log_warning "Lalu jalankan 'update-grub' atau 'grub-mkconfig -o /boot/grub/grub.cfg' untuk mencegah freeze saat booting."
    fi
}

format_swap_partition() {
    local dev="$1"

    check_root || return 1

    if [[ ! -b "$dev" ]]; then
        log_error "Device partisi '$dev' tidak valid atau tidak ditemukan."
        return 1
    fi

    local old_uuid
    old_uuid=$(get_partition_uuid "$dev")

    if [[ -n "$old_uuid" ]]; then
        log_info "Mempertahankan UUID partisi lama ($old_uuid)..."
        mkswap -U "$old_uuid" "$dev"
        local status=$?
        if [[ $status -ne 0 ]]; then
            log_error "Gagal menjalankan mkswap -U pada $dev (Exit code: $status)"
            return $status
        fi
        log_success "Partisi $dev berhasil diformat ulang dengan UUID tetap ($old_uuid)."
    else
        log_info "Tidak ada UUID lama terdeteksi. Membuat swap baru pada $dev..."
        mkswap "$dev"
        local status=$?
        if [[ $status -ne 0 ]]; then
            log_error "Gagal menjalankan mkswap pada $dev (Exit code: $status)"
            return $status
        fi

        local new_uuid
        new_uuid=$(get_partition_uuid "$dev")
        log_success "Partisi $dev berhasil diformat dengan UUID baru ($new_uuid)."

        if [[ -n "$new_uuid" ]]; then
            check_grub_resume "$new_uuid"
        fi
    fi

    return 0
}

# ---------------------------------------------------------
# 2. Penanganan Swapfile (Btrfs vs Standar)
# ---------------------------------------------------------
create_swapfile() {
    local swap_path="$1"
    local size_str="$2"   # Contoh: 8G, 4096M
    local mib_count="$3"  # Ukuran dalam MiB untuk dd (contoh: 8192)

    check_root || return 1

    if [[ -z "$swap_path" || -z "$size_str" ]]; then
        log_error "Penggunaan: create_swapfile <path> <size_str> [mib_count]"
        return 1
    fi

    local dir_path
    dir_path=$(dirname "$(realpath -m "$swap_path")")

    if [[ ! -d "$dir_path" ]]; then
        log_error "Direktori target '$dir_path' tidak ditemukan."
        return 1
    fi

    # Deteksi Filesystem
    local fs_type=""
    fs_type=$(df -T "$dir_path" 2>/dev/null | tail -n 1 | awk '{print $2}')
    if [[ -z "$fs_type" ]]; then
        fs_type=$(stat -f -c %T "$dir_path" 2>/dev/null)
    fi

    log_info "Tipe filesystem pada '$dir_path': $fs_type"

    # Penanganan Khusus Btrfs
    if [[ "$fs_type" =~ ^[Bb][Tt][Rr][Ff][Ss]$ ]]; then
        log_info "Mendeteksi sistem berkas Btrfs."
        
        # 1. Coba btrfs filesystem mkswapfile bawaan
        if command -v btrfs &>/dev/null; then
            log_info "Mencoba membuat swapfile menggunakan 'btrfs filesystem mkswapfile'..."
            btrfs filesystem mkswapfile --size "$size_str" "$swap_path"
            if [[ $? -eq 0 ]]; then
                log_success "Swapfile Btrfs berhasil dibuat di $swap_path"
                return 0
            else
                log_warning "'btrfs filesystem mkswapfile' gagal/tidak didukung. Menggunakan alur fallback manual..."
            fi
        fi

        # 2. Fallback Manual Btrfs
        log_info "Menyiapkan swapfile Btrfs secara manual (NoCoW & uncompressed)..."
        touch "$swap_path" && truncate -s 0 "$swap_path"
        if [[ $? -ne 0 ]]; then
            log_error "Gagal membuat/mengosongkan file target di $swap_path"
            return 1
        fi

        chattr +C "$swap_path"
        if [[ $? -ne 0 ]]; then
            log_warning "Gagal menetapkan atribut NoCoW (+C) pada $swap_path"
        fi

        if command -v btrfs &>/dev/null; then
            btrfs property set "$swap_path" compression none 2>/dev/null
        fi

        if [[ -z "$mib_count" ]]; then
            # Ekstrak perkiraan MiB jika tidak disediakan
            local num unit
            num=$(echo "$size_str" | grep -o -E '^[0-9]+')
            unit=$(echo "$size_str" | grep -o -E '[a-zA-Z]+' | tr '[:lower:]' '[:upper:]')
            if [[ "$unit" =~ G ]]; then
                mib_count=$(( num * 1024 ))
            elif [[ "$unit" =~ M ]]; then
                mib_count=$num
            else
                mib_count=1024
            fi
        fi

        log_info "Mengalokasikan file dengan dd (ukuran: ${mib_count}MiB)..."
        dd if=/dev/zero of="$swap_path" bs=1M count="$mib_count" status=progress
        if [[ $? -ne 0 ]]; then
            log_error "Gagal mengalokasikan data ke $swap_path menggunakan dd"
            rm -f "$swap_path"
            return 1
        fi

        chmod 600 "$swap_path"
        mkswap "$swap_path"
        if [[ $? -ne 0 ]]; then
            log_error "Gagal menjalankan mkswap pada $swap_path"
            return 1
        fi

        log_success "Swapfile Btrfs manual berhasil dibuat dan diformat di $swap_path"
        return 0
    fi

    # Penanganan Filesystem Standar (ext4, xfs, dll.)
    log_info "Mengalokasikan swapfile pada filesystem standar ($fs_type)..."
    local allocated=0

    if command -v fallocate &>/dev/null; then
        fallocate -l "$size_str" "$swap_path" 2>/dev/null
        if [[ $? -eq 0 ]]; then
            allocated=1
        fi
    fi

    if [[ $allocated -eq 0 ]]; then
        log_warning "fallocate tidak tersedia atau gagal. Menggunakan fallback dd..."
        if [[ -z "$mib_count" ]]; then
            local num unit
            num=$(echo "$size_str" | grep -o -E '^[0-9]+')
            unit=$(echo "$size_str" | grep -o -E '[a-zA-Z]+' | tr '[:lower:]' '[:upper:]')
            if [[ "$unit" =~ G ]]; then
                mib_count=$(( num * 1024 ))
            elif [[ "$unit" =~ M ]]; then
                mib_count=$num
            else
                mib_count=1024
            fi
        fi

        dd if=/dev/zero of="$swap_path" bs=1M count="$mib_count" status=progress
        if [[ $? -ne 0 ]]; then
            log_error "Gagal membuat file swap dengan dd."
            rm -f "$swap_path"
            return 1
        fi
    fi

    chmod 600 "$swap_path"
    mkswap "$swap_path"
    if [[ $? -ne 0 ]]; then
        log_error "Gagal menjalankan mkswap pada $swap_path"
        return 1
    fi

    log_success "Swapfile berhasil dibuat di $swap_path"
    return 0
}

# ---------------------------------------------------------
# 3. Sanitasi dan Pencegahan Duplikasi di /etc/fstab
# ---------------------------------------------------------
backup_fstab() {
    check_root || return 1

    local backup_path="/etc/fstab.bak.$(date +%s)"
    cp /etc/fstab "$backup_path"
    if [[ $? -ne 0 ]]; then
        log_error "Gagal membuat backup /etc/fstab!"
        return 1
    fi
    log_info "Backup fstab tersimpan di: $backup_path"
    return 0
}

remove_swap_from_fstab() {
    local target="$1"
    local uuid="$2"

    check_root || return 1
    [[ -z "$target" ]] && return 1

    backup_fstab || return 1

    # Sanitasi sed: Hapus entri yang mengandung path target
    # Menggunakan pemisah # untuk menghindari konflik dengan karakter slash /
    sed -i "\|[[:space:]]*${target}[[:space:]]|d; \|[[:space:]]*${target}$|d" /etc/fstab

    # Jika UUID disertakan, hapus entri UUID yang cocok
    if [[ -n "$uuid" ]]; then
        sed -i "\|[[:space:]]*UUID=${uuid}[[:space:]]|d; \|[[:space:]]*UUID=${uuid}$|d" /etc/fstab
    fi

    log_info "Entri lama untuk '$target' dibersihkan dari /etc/fstab."
    return 0
}

add_swap_to_fstab() {
    local target="$1"
    local priority="$2"
    local is_block="$3" # 1 jika block device/partition, 0 jika swapfile

    check_root || return 1
    [[ -z "$target" ]] && return 1

    local uuid=""
    if [[ "$is_block" == "1" || -b "$target" ]]; then
        uuid=$(get_partition_uuid "$target")
    fi

    # Bersihkan entri duplikat sebelumnya
    remove_swap_from_fstab "$target" "$uuid"

    local options="defaults"
    if [[ -n "$priority" ]]; then
        options="defaults,pri=${priority}"
    fi

    local entry_target="$target"
    if [[ -n "$uuid" ]]; then
        entry_target="UUID=${uuid}"
    fi

    echo -e "${entry_target}\tnone\tswap\t${options}\t0\t0" >> /etc/fstab
    if [[ $? -eq 0 ]]; then
        log_success "Entri swap berhasil ditambahkan ke /etc/fstab: ${entry_target}"
        return 0
    else
        log_error "Gagal menulis ke /etc/fstab!"
        return 1
    fi
}

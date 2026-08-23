const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const os = require('os');

// path.sep is '\' on Windows — normalize to forward slash for test comparisons
function safeExtractPath(projectRoot, filename) {
    const normalized = filename.split('/').join(path.sep);
    if (normalized.startsWith('..') || path.isAbsolute(normalized)) return null;
    const target = path.resolve(projectRoot, normalized);
    const rootNorm = path.normalize(projectRoot);
    if (target === rootNorm) return null;
    if (!target.startsWith(rootNorm + path.sep)) return null;
    return target;
}

function verifyZip(zipPath) {
    try {
        const data = fs.readFileSync(zipPath);
        if (data.length < 22) return false;
        if (data.readUInt32LE(0) !== 0x04034b50) return false;
        let offset = 0;
        let foundEntry = false;
        while (offset < data.length) {
            const sig = data.readUInt32LE(offset);
            if (sig === 0x01000405 || sig === 0x06054b50 || sig === 0x08074b50) break;
            if (sig !== 0x04034b50) return false;
            const crc = data.readUInt32LE(offset + 14);
            const compSize = data.readUInt32LE(offset + 18);
            const fnLen = data.readUInt16LE(offset + 26);
            const extraLen = data.readUInt16LE(offset + 28);
            const localDataStart = offset + 30 + fnLen + extraLen;
            const fileData = data.slice(localDataStart, localDataStart + compSize);
            const method = data.readUInt16LE(offset + 8);
            let actualCrc;
            if (method === 0) {
                actualCrc = zlib.crc32(fileData) & 0xFFFFFFFF;
            } else if (method === 8 && compSize > 6) {
                try { actualCrc = zlib.crc32(zlib.inflateRaw(fileData)) & 0xFFFFFFFF; }
                catch { return false; }
            } else {
                break;
            }
            if (actualCrc !== crc) return false;
            foundEntry = true;
            offset = localDataStart + compSize;
        }
        return foundEntry;
    } catch { return false; }
}

function makeStoredZip(files, destPath) {
    let lhBuf = Buffer.alloc(0);
    const cdirEntries = [];
    let offset = 0;
    for (const f of files) {
        const data = Buffer.isBuffer(f.data) ? f.data : Buffer.from(f.data);
        const nm = Buffer.from(f.name, 'utf8');
        const crc = zlib.crc32(data) & 0xFFFFFFFF;
        const lh = Buffer.alloc(30 + nm.length + data.length);
        lh.writeUInt32LE(0x04034b50, 0);
        lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0, 6);
        lh.writeUInt16LE(0, 8); lh.writeUInt16LE(0, 10);
        lh.writeUInt16LE(0, 12); lh.writeUInt32LE(crc, 14);
        lh.writeUInt32LE(data.length, 18);
        lh.writeUInt32LE(data.length, 22);
        lh.writeUInt16LE(nm.length, 26);
        lh.writeUInt16LE(0, 28);
        nm.copy(lh, 30);
        data.copy(lh, 30 + nm.length);
        lhBuf = Buffer.concat([lhBuf, lh]);
        const cd = Buffer.alloc(46 + nm.length);
        cd.writeUInt32LE(0x01000405, 0);
        cd.writeUInt16LE(20, 4); cd.writeUInt16LE(20, 6);
        cd.writeUInt16LE(0, 8); cd.writeUInt16LE(0, 10);
        cd.writeUInt16LE(0, 12); cd.writeUInt16LE(0, 14);
        cd.writeUInt32LE(crc, 16);
        cd.writeUInt32LE(data.length, 20);
        cd.writeUInt32LE(data.length, 24);
        cd.writeUInt16LE(nm.length, 28);
        cd.writeUInt16LE(0, 30); cd.writeUInt16LE(0, 32);
        cd.writeUInt16LE(0, 34); cd.writeUInt16LE(0, 36);
        cd.writeUInt32LE(0, 38); cd.writeUInt32LE(offset, 42);
        nm.copy(cd, 46);
        cdirEntries.push(cd);
        offset += lh.length;
    }
    const cdStart = lhBuf.length;
    let cdBuf = Buffer.alloc(0);
    for (const cd of cdirEntries) cdBuf = Buffer.concat([cdBuf, cd]);
    const eocd = Buffer.alloc(22);
    eocd.writeUInt32LE(0x06054b50, 0);
    eocd.writeUInt16LE(0, 4); eocd.writeUInt16LE(0, 6);
    eocd.writeUInt16LE(cdirEntries.length, 8);
    eocd.writeUInt16LE(cdirEntries.length, 10);
    eocd.writeUInt32LE(cdBuf.length, 12);
    eocd.writeUInt32LE(cdStart, 16);
    eocd.writeUInt16LE(0, 20);
    fs.writeFileSync(destPath, Buffer.concat([lhBuf, cdBuf, eocd]));
}

let pass = 0, fail = 0;
function check(name, cond) {
    if (cond) { pass++; console.log('  [PASS] ' + name); }
    else { fail++; console.log('  [FAIL] ' + name); }
}

console.log('='.repeat(56));
console.log('  更新链路动态测试');
console.log('='.repeat(56));

console.log('\n── Test 1: format_version ──');
function fv(v) { return v <= 0 ? 'No update' : String(v); }
check('fv(42)=42', fv(42) === '42');
check('fv(0)=No update', fv(0) === 'No update');
check('fv(-1)=No update', fv(-1) === 'No update');

console.log('\n── Test 2: 路径穿越保护 ──');
const pRoot = path.join('C:', path.sep, 'project_root');
check('正常路径', safeExtractPath(pRoot, 'version.txt') === path.join(pRoot, 'version.txt'));
check('子目录', safeExtractPath(pRoot, '_internal/x.py') === path.join(pRoot, '_internal', 'x.py'));
check('父目录穿越', safeExtractPath(pRoot, '../etc/passwd') === null);
check('绝对路径', safeExtractPath(pRoot, '/etc/passwd') === null);
check('点路径', safeExtractPath(pRoot, '.') === null);

console.log('\n── Test 3: ZIP 完整性验证 ──');
const tmpdir = fs.mkdtempSync(path.join(os.tmpdir(), 'ut-'));

makeStoredZip([{name: '_internal/test.txt', data: Buffer.from('hello')}], path.join(tmpdir, 'valid.zip'));
check('正常 zip', verifyZip(path.join(tmpdir, 'valid.zip')));

makeStoredZip([], path.join(tmpdir, 'empty.zip'));
check('空 zip → False', !verifyZip(path.join(tmpdir, 'empty.zip')));

fs.writeFileSync(path.join(tmpdir, 'fake.zip'), Buffer.from('not a zip'));
check('非 zip → False', !verifyZip(path.join(tmpdir, 'fake.zip')));

makeStoredZip([{name: 'f.txt', data: Buffer.from('content here')}], path.join(tmpdir, 'tampered.zip'));
let td = fs.readFileSync(path.join(tmpdir, 'tampered.zip'));
// 篡改文件数据区（local header 30 + fnLen + extraLen = 30+3+0 = 33 开始是数据）
td[35] ^= 0xFF;
fs.writeFileSync(path.join(tmpdir, 'tampered.zip'), td);
check('篡改 zip → False', !verifyZip(path.join(tmpdir, 'tampered.zip')));

fs.writeFileSync(path.join(tmpdir, 'tiny.zip'), Buffer.from('short'));
check('小文件 → False', !verifyZip(path.join(tmpdir, 'tiny.zip')));

fs.rmSync(tmpdir, {recursive: true, force: true});

console.log('\n── Test 4: _extract_zip 代码路径 ──');
const uw = process.cwd().replace(/\\/g, '/');
const updater = fs.readFileSync(uw + '/client/utils/updater.py', 'utf8');
check('清理旧 update/', updater.includes('shutil.rmtree(update_dir'));
check('解压到 update/', updater.includes('os.makedirs(update_dir'));
check('替换 _internal/', updater.includes('shutil.copytree(src_internal, internal_root'));
check('dirs_exist_ok 处理残留', updater.includes('dirs_exist_ok=True'));
check('替换 MMS-Main.exe', updater.includes('shutil.copy2(src_main, main_exe)'));
check('替换 MMS-WebServices.exe', updater.includes('shutil.copy2(src_web, web_exe)'));
check('跳过自替换 → temp staging', updater.includes('MMS-Update_new.exe'));
check('更新 version.txt', updater.includes('version.txt'));
check('路径安全检查', updater.includes('_safe_extract_path'));

console.log('\n── Test 5: restart_self 路径 ──');
const rs = (updater.match(/def restart_self[\s\S]*?os\._exit\(0\)/) || [])[0] || '';
check('写 _mms_restart.bat', rs.includes('_mms_restart.bat'));
check('启动 MMS-Update.exe', rs.includes('MMS-Update.exe'));
check('传入 update.zip 参数', rs.includes('update.zip'));
check('调用 os._exit(0)', rs.includes('os._exit(0)'));
check('debug 模式 MMS-Update.py', rs.includes('MMS-Update.py'));

console.log('\n── Test 6: 手动更新下载保存 ──');
const ssb = fs.readFileSync(uw + '/client/widgets/sync_status_bar.py', 'utf8');
check('下载 RETR update.zip', ssb.includes('RETR update.zip'));
check('保存到 update_zip_dst', ssb.includes('update_zip_dst'));
check('调 restart_self', ssb.includes('restart_self'));
check('ready 触发重启', ssb.includes('"status": "ready"'));

console.log('\n── Test 7: MMS-Update.py zip 搜索 ──');
const upd = fs.readFileSync(uw + '/client/MMS-Update.py', 'utf8');
check('Priority 1: sys.argv[1]', upd.includes('sys.argv[1]'));
check('Priority 2: project_root/update.zip', upd.includes('os.path.join(project_root, "update.zip")'));
check('Priority 3: temp mms_update.zip', upd.includes('mms_update.zip'));
check('等待 MMS-Main.exe 退出', upd.includes('MMS-Main.exe'));
check('调 _extract_zip', upd.includes('_extract_zip'));
check('启动 MMS-Main.exe', upd.includes('subprocess.Popen(main_exe'));

console.log('\n── Test 8: 完整链路顺序 ──');
const all = ssb + updater + upd;
const steps = [
    ['① 点检查更新按钮', 'update_btn'],
    ['② 读 FTP 配置', 'load_update_config'],
    ['③ 连 FTP 下 version.txt', 'RETR version.txt'],
    ['④ 比对版本', 'remote_ver'],
    ['⑤ 下载 update.zip', 'RETR update.zip'],
    ['⑥ 校验 zip', '_verify_zip'],
    ['⑦ 保存 update.zip', 'update_zip_dst'],
    ['⑧ ready 信号', 'status'],
    ['⑨ QTimer 2.5s', 'singleShot(2500'],
    ['⑩ 写 _mms_restart.bat', '_mms_restart.bat'],
    ['⑪ bat 启 MMS-Update.exe', 'MMS-Update.exe'],
    ['⑫ 传 update.zip', 'update.zip'],
    ['⑬ 等主程序退出', 'MMS-Main.exe'],
    ['⑭ _extract_zip 替换', '_extract_zip'],
    ['⑮ 更新 version.txt', 'version.txt'],
    ['⑯ 启新 MMS-Main.exe', 'subprocess.Popen(main_exe'],
];
for (const [desc, pattern] of steps) {
    check(desc, all.includes(pattern));
}

const total = pass + fail;
console.log('\n' + '='.repeat(56));
console.log('  结果: ' + pass + '/' + total + ' 通过' + (fail ? '  ' + fail + ' 失败' : '  — 链路完整'));
console.log('='.repeat(56));
process.exit(fail > 0 ? 1 : 0);
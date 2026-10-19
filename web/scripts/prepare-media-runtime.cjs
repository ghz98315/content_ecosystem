const fs=require('node:fs'),path=require('node:path');
const destination=path.resolve(__dirname,'../public/media-runtime/v0.12.10');fs.mkdirSync(destination,{recursive:true});
const core=path.dirname(require.resolve('@ffmpeg/core')).replace(/[\\/]umd$/,'/esm');
for(const name of ['ffmpeg-core.js','ffmpeg-core.wasm'])fs.copyFileSync(path.join(core,name),path.join(destination,name));
// Serve the module worker unchanged: bundlers rewrite its dynamic core import.
const wrapper=path.dirname(require.resolve('@ffmpeg/ffmpeg/worker'));
const workerDestination=path.resolve(__dirname,'../public/media-runtime/wrapper-v0.12.15');
fs.mkdirSync(workerDestination,{recursive:true});
for(const name of ['worker.js','const.js','errors.js'])fs.copyFileSync(path.join(wrapper,name),path.join(workerDestination,name));
fs.copyFileSync(path.join(__dirname,'FFMPEG-WRAPPER-LICENSE.txt'),path.join(workerDestination,'LICENSE.txt'));
fs.copyFileSync(path.join(__dirname,'FFMPEG-COPYING.GPLv2.txt'),path.join(destination,'COPYING.GPLv2.txt'));
fs.writeFileSync(path.join(destination,'SOURCE.txt'),'FFmpeg WebAssembly core 0.12.10, GPL-2.0-or-later.\nCorresponding source and build instructions: https://github.com/ffmpegwasm/ffmpeg.wasm\nPackage source: https://registry.npmjs.org/@ffmpeg/core/-/core-0.12.10.tgz\nNo local modifications to the runtime.\n');
console.log('Local media runtime prepared');

export function avatarSize(width: number, height: number) {
  if (width <= 0 || height <= 0) throw new Error('Не удалось определить размер изображения');
  if (width * height > 40000000 || Math.max(width,height) > 20000) throw new Error('Изображение слишком большое. Выберите фото до 40 мегапикселей.');
  const scale=Math.min(1,512/Math.max(width,height));
  return {width:Math.max(1,Math.round(width*scale)),height:Math.max(1,Math.round(height*scale))};
}
/** Resize on this device; only the resulting avatar is saved with the profile. */
export async function prepareAvatar(file: File): Promise<string> {
  if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 10*1024*1024) throw new Error('Выберите PNG, JPEG или WebP не более 10 МБ');
  const url=URL.createObjectURL(file);
  try {
    const image=new Image(); image.src=url;
    try { await image.decode(); } catch { throw new Error('Не удалось прочитать фото. Выберите другое изображение.'); }
    const {width,height}=avatarSize(image.naturalWidth,image.naturalHeight);
    const canvas=document.createElement('canvas'); canvas.width=width; canvas.height=height;
    const context=canvas.getContext('2d');
    if (!context) throw new Error('Не удалось обработать фото. Попробуйте другой браузер.');
    context.drawImage(image,0,0,width,height);
    for (const quality of [.86,.7,.54,.38]) {
      const blob=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,'image/webp',quality));
      if (!blob) throw new Error('Не удалось сжать фото. Выберите другое изображение.');
      if (blob.size <= 256*1024) return await new Promise<string>((resolve,reject)=>{
        const reader=new FileReader(); reader.onload=()=>resolve(String(reader.result));
        reader.onerror=()=>reject(new Error('Не удалось прочитать обработанное фото')); reader.readAsDataURL(blob);
      });
    }
    throw new Error('Не удалось уменьшить фото до допустимого размера. Выберите другое изображение.');
  } finally { URL.revokeObjectURL(url); }
}

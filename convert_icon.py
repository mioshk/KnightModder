from PIL import Image

# 打开 PNG 文件
img = Image.open('assets/icon.png')
# 保存为 ICO 格式（支持多尺寸）
img.save('assets/icon.ico', format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
print("图标转换完成！")
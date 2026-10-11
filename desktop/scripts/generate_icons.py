import math
import os
from PIL import Image, ImageDraw

def create_jarvis_icon(size=512):
    # High resolution image with alpha channel
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = size / 2
    
    # Outer dark glow
    for r in range(int(size * 0.48), int(size * 0.44), -1):
        alpha = int(40 * (size * 0.48 - r) / (size * 0.04))
        draw.ellipse([center - r, center - r, center + r, center + r], 
                     outline=(11, 23, 34, alpha), width=2)
    
    # Dark outer circular backing
    backing_r = int(size * 0.45)
    draw.ellipse([center - backing_r, center - backing_r, center + backing_r, center + backing_r],
                 fill=(6, 8, 12, 245), outline=(13, 75, 104, 255), width=int(size * 0.015))
    
    # Neon cyan outer reactor ring
    ring1_r = int(size * 0.41)
    draw.ellipse([center - ring1_r, center - ring1_r, center + ring1_r, center + ring1_r],
                 outline=(39, 211, 255, 180), width=int(size * 0.01))
                 
    # Segmented arc tracks
    num_segments = 12
    segment_r = int(size * 0.36)
    seg_width = int(size * 0.035)
    for i in range(num_segments):
        start_angle = i * (360 / num_segments) + 6
        end_angle = (i + 1) * (360 / num_segments) - 6
        draw.arc([center - segment_r, center - segment_r, center + segment_r, center + segment_r],
                 start=start_angle, end=end_angle, fill=(39, 211, 255, 230), width=seg_width)
                 
    # Intermediate technical circuit ring
    circuit_r = int(size * 0.28)
    draw.ellipse([center - circuit_r, center - circuit_r, center + circuit_r, center + circuit_r],
                 outline=(13, 75, 104, 200), width=int(size * 0.008))
                 
    # Inner energy arcs
    inner_arcs = 6
    inner_arc_r = int(size * 0.23)
    for i in range(inner_arcs):
        start_a = i * (360 / inner_arcs) + 12
        end_a = (i + 1) * (360 / inner_arcs) - 12
        draw.arc([center - inner_arc_r, center - inner_arc_r, center + inner_arc_r, center + inner_arc_r],
                 start=start_a, end=end_a, fill=(39, 211, 255, 255), width=int(size * 0.025))
                 
    # Central reactor core glow
    for r in range(int(size * 0.16), int(size * 0.05), -1):
        glow_alpha = int(180 * (size * 0.16 - r) / (size * 0.11))
        draw.ellipse([center - r, center - r, center + r, center + r],
                     fill=(39, 211, 255, glow_alpha))
                     
    # Center white-hot core
    core_r = int(size * 0.08)
    draw.ellipse([center - core_r, center - core_r, center + core_r, center + core_r],
                 fill=(225, 248, 255, 255), outline=(39, 211, 255, 255), width=int(size * 0.01))
                 
    # Small center pupil
    pupil_r = int(size * 0.035)
    draw.ellipse([center - pupil_r, center - pupil_r, center + pupil_r, center + pupil_r],
                 fill=(255, 255, 255, 255))
                 
    return img

def main():
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    
    # 512x512 Master icon
    master_img = create_jarvis_icon(512)
    png_path = os.path.join(assets_dir, 'icon.png')
    master_img.save(png_path, format='PNG')
    print(f"Generated {png_path}")
    
    # Tray icon (32x32)
    tray_img = create_jarvis_icon(64).resize((32, 32), Image.Resampling.LANCZOS)
    tray_path = os.path.join(assets_dir, 'tray-icon.png')
    tray_img.save(tray_path, format='PNG')
    print(f"Generated {tray_path}")
    
    # Multi-resolution ICO for Windows
    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_images = [master_img.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]
    ico_path = os.path.join(assets_dir, 'icon.ico')
    ico_images[0].save(
        ico_path,
        format='ICO',
        sizes=ico_sizes,
        append_images=ico_images[1:]
    )
    print(f"Generated multi-resolution Windows ICO: {ico_path}")

if __name__ == '__main__':
    main()

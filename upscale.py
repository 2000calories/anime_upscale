import os
import subprocess
import glob
import re
import shutil
import time

# List of input files
input_files = [
    "04 - 葫芦兄弟（葫芦娃）第4集（1986）.mp4",
    "05 - 葫芦兄弟（葫芦娃）第5集（1986）.mp4",
]

for input_file in input_files:
    base_name = os.path.splitext(os.path.basename(input_file))[0]

    # Step 1: Extract frames
    frames_dir = f"frames_{base_name}"
    os.makedirs(frames_dir, exist_ok=True)
    subprocess.run(["ffmpeg", "-i", input_file, f"frames_{base_name}/frame_%06d.png"])

    # Step 2: Extract frame rate
    result = subprocess.run(
        ["ffmpeg", "-i", input_file], stderr=subprocess.PIPE, text=True
    )
    frame_rate_line = [line for line in result.stderr.split("\n") if "fps" in line][0]
    frame_rate = float(frame_rate_line.split("fps")[0].split()[-1])

    # Step 3: Get total number of frames
    extracted_frames = glob.glob(f"{frames_dir}/frame_*.png")
    if not extracted_frames:
        print(
            f"No frames extracted for {input_file}. Check the ffmpeg command and paths."
        )
        continue  # Skip to the next file if no frames were extracted

    total_frames = len(extracted_frames)
    print(f"Total frames extracted for {input_file}: {total_frames}")

    # Step 4: Calculate frames per minute
    frames_per_minute = int(frame_rate * 60)

    # Step 5: Process frames in chunks
    os.makedirs(f"upscaled_frames_{base_name}", exist_ok=True)
    chunk_start = 1
    chunk_end = frames_per_minute
    chunk_index = 1

    total_time_taken = 0
    processed_frames = 0

    while chunk_start <= total_frames:

        # Check if the chunk video already exists
        chunk_video_path = f"upscaled_video_chunk_{base_name}_{chunk_index}.mp4"
        if os.path.exists(chunk_video_path):
            print(
                f"Chunk video {chunk_video_path} already exists. Skipping to next chunk."
            )
            chunk_start = chunk_end + 1
            chunk_end += frames_per_minute
            chunk_index += 1
            continue

        start_time = time.time()  # Start time for the chunk processing

        print(f"Processing chunk {chunk_index}: frames {chunk_start} to {chunk_end}")
        os.makedirs(f"chunk_{base_name}_{chunk_index}", exist_ok=True)

        for i in range(chunk_start, min(chunk_end, total_frames) + 1):
            frame = f"frames_{base_name}/frame_{i:06d}.png"
            subprocess.run(["cp", frame, f"chunk_{base_name}_{chunk_index}/"])

        os.makedirs(f"upscaled_frames_{base_name}/chunk_{chunk_index}", exist_ok=True)

        subprocess.run(
            [
                "./realcugan-ncnn-vulkan",
                "-i",
                f"chunk_{base_name}_{chunk_index}/",
                "-o",
                f"upscaled_frames_{base_name}/chunk_{chunk_index}/",
                "-m",
                "models-pro",
                "-n",
                "3",
                "-t",
                "5000",# change to 0 to reduce memory usage
                "-c",
                "2",
            ]
        )

        result = subprocess.run(
            [
                "ffmpeg",
                "-framerate",
                str(frame_rate),
                "-start_number",
                str(chunk_start),
                "-i",
                f"upscaled_frames_{base_name}/chunk_{chunk_index}/frame_%06d.png",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                f"upscaled_video_chunk_{base_name}_{chunk_index}.mp4",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            print(
                f"Error generating upscaled_video_chunk_{base_name}_{chunk_index}.mp4: {result.stderr}"
            )
        else:
            print(
                f"Successfully generated upscaled_video_chunk_{base_name}_{chunk_index}.mp4"
            )

        subprocess.run(["rm", "-r", f"chunk_{base_name}_{chunk_index}"])
        subprocess.run(["rm", "-r", f"upscaled_frames_{base_name}/chunk_{chunk_index}"])


        end_time = time.time()  # End time for the chunk processing
        chunk_time_taken = end_time - start_time
        total_time_taken += chunk_time_taken
        processed_frames += min(chunk_end, total_frames) - chunk_start + 1

        # Calculate and print estimated remaining time
        average_time_per_frame = total_time_taken / processed_frames
        remaining_frames = total_frames - processed_frames
        estimated_remaining_time = average_time_per_frame * remaining_frames
        print(
            f"Time taken for chunk {chunk_index}: {chunk_time_taken:.2f} seconds"
        )
        print(
            f"Estimated remaining time: {estimated_remaining_time / 60:.2f} minutes"
        )

        chunk_start = chunk_end + 1
        chunk_end += frames_per_minute
        chunk_index += 1

    # Step 6: Concatenate video chunks
    def numerical_sort(value):
        numbers = re.findall(r"_(\d+)\.mp4$", value)
        return int(numbers[0]) if numbers else 0

    with open(f"file_list_{base_name}.txt", "w") as f:
        for video_chunk in sorted(
            glob.glob(f"upscaled_video_chunk_{base_name}_*.mp4"), key=numerical_sort
        ):
            f.write(f"file '{os.path.abspath(video_chunk)}'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            f"file_list_{base_name}.txt",
            "-c",
            "copy",
            "-y",
            f"upscaled_video_{base_name}.mp4",
        ]
    )

    # Step 7: Extract audio
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            input_file,
            "-q:a",
            "0",
            "-map",
            "a",
            "-y",
            f"audio_{base_name}.aac",
        ]
    )

    # Step 8: Combine upscaled video with original audio
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            f"upscaled_video_{base_name}.mp4",
            "-i",
            f"audio_{base_name}.aac",
            "-c:v",
            "copy",
            "-y",
            "-c:a",
            "aac",
            "-strict",
            "experimental",
            f"upscaled_{input_file}",
        ]
    )

    # Cleanup
    for file in glob.glob(f"upscaled_video_chunk_{base_name}_*.mp4"):
        os.remove(file)
    os.remove(f"upscaled_video_{base_name}.mp4")
    os.remove(f"file_list_{base_name}.txt")
    os.remove(f"audio_{base_name}.aac")
    shutil.rmtree(f"frames_{base_name}")
    shutil.rmtree(f"upscaled_frames_{base_name}")

import carla
import math
import random
import time
import queue
import numpy as np
import cv2
import os
from transformers import AutoTokenizer, AutoImageProcessor, VisionEncoderDecoderModel, AutoModelForCausalLM
from PIL import Image

client = carla.Client('localhost', 2000)
world  = client.get_world()
bp_lib = world.get_blueprint_library()

# Get the map spawn points
spawn_points = world.get_map().get_spawn_points()

# spawn vehicle
vehicle_bp = bp_lib.find('vehicle.lincoln.mkz')
vehicle = world.try_spawn_actor(vehicle_bp, random.choice(spawn_points))

vehicle.set_autopilot(True)

# Set up the simulator in synchronous mode
settings = world.get_settings()
settings.synchronous_mode = True # Enables synchronous mode
settings.fixed_delta_seconds = 0.05
world.apply_settings(settings)

# Create a queue to store and retrieve the sensor data
image_queue = queue.Queue()
#camera.listen(image_queue.put)
semantic_queue = queue.Queue()
#camera2.listen(semantic_queue.put)

# Create output directories
os.makedirs('ims', exist_ok=True)
os.makedirs('labels', exist_ok=True)

# Initialize AI models
print("Loading image captioning model...")
model_path = "cnmoro/mini-image-captioning"
caption_model = VisionEncoderDecoderModel.from_pretrained(model_path)
caption_tokenizer = AutoTokenizer.from_pretrained(model_path)
image_processor = AutoImageProcessor.from_pretrained(model_path)

print("Loading language model...")
llm_model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0" # "Qwen/Qwen3-0.6B" # "arnir0/Tiny-LLM" # "Qwen/Qwen3-0.6B"
llm_tokenizer = AutoTokenizer.from_pretrained(llm_model_name)
llm_model = AutoModelForCausalLM.from_pretrained(
    llm_model_name,
    torch_dtype="auto",
    device_map="auto"
)

# Spawn 10 pedestrians with cameras
print("Spawning pedestrians...")
pedestrians = []
pedestrian_cameras = []
pedestrian_queues = []
pedestrian_histories = []

walker_bp = bp_lib.filter('walker.pedestrian.*')
for i in range(3):
    # Spawn pedestrian
    spawn_point = random.choice(spawn_points)
    ped_bp = random.choice(walker_bp)
    pedestrian = world.try_spawn_actor(ped_bp, spawn_point)
    
    if pedestrian:
        # Spawn camera attached to pedestrian
        ped_camera_bp = bp_lib.find('sensor.camera.rgb')
        ped_camera_bp.set_attribute('image_size_x', '640')
        ped_camera_bp.set_attribute('image_size_y', '480')
        ped_camera_trans = carla.Transform(carla.Location(x=0.5, z=1.7))  # Eye level
        ped_camera = world.spawn_actor(ped_camera_bp, ped_camera_trans, attach_to=pedestrian)
        
        # Create queue for this pedestrian's camera
        ped_queue = queue.Queue()
        ped_camera.listen(ped_queue.put)
        
        pedestrians.append(pedestrian)
        pedestrian_cameras.append(ped_camera)
        pedestrian_queues.append(ped_queue)
        pedestrian_histories.append({'observations': [], 'decisions': []})
        
        # Set pedestrian to walk randomly
        walker_controller_bp = world.get_blueprint_library().find('controller.ai.walker')
        walker_controller = world.spawn_actor(walker_controller_bp, carla.Transform(), pedestrian)
        walker_controller.start()
        walker_controller.go_to_location(world.get_random_location_from_navigation())
        walker_controller.set_max_speed(1.4)  # Normal walking speed
        
        print(f"Spawned pedestrian {i+1}")

print(f"Successfully spawned {len(pedestrians)} pedestrians")



def check_bbox_has_vehicle(points_2d, semantic_img, img_w, img_h):
    """
    Check if bounding box contains vehicle pixels in semantic segmentation.
    Vehicle labels are 12-19 (inclusive) in the red channel.
    """
    # Get bounding rectangle
    x_coords = points_2d[:, 0]
    y_coords = points_2d[:, 1]
    
    x_min = max(0, int(np.min(x_coords)))
    x_max = min(img_w - 1, int(np.max(x_coords)))
    y_min = max(0, int(np.min(y_coords)))
    y_max = min(img_h - 1, int(np.max(y_coords)))
    
    if x_max <= x_min or y_max <= y_min:
        return False
    
    # Extract ROI from semantic image
    roi = semantic_img[y_min:y_max, x_min:x_max, 2]  # Red channel
    # Check if any pixels in ROI are vehicle labels (12-19)
    vehicle_pixels = np.sum((roi >= 12) & (roi <= 19))
    
    # Require at least some vehicle pixels
    return vehicle_pixels > 0


def process_pedestrian_vision(ped_idx, ped_image):
    """
    Process pedestrian's camera image through AI models.
    Returns the caption and decision.
    """
    # Convert CARLA image to PIL Image
    print('thinking', ped_idx)
    img_array = np.reshape(np.copy(ped_image.raw_data), (ped_image.height, ped_image.width, 4))
    img_rgb = img_array[:, :, :3]  # Remove alpha channel
    pil_image = Image.fromarray(img_rgb)
    
    # Generate caption
    pixel_values = image_processor(pil_image, return_tensors="pt").pixel_values
    start_caption = time.time()
    generated_ids = caption_model.generate(pixel_values, temperature=0.7, top_p=0.8, top_k=50, num_beams=1)
    generated_caption = caption_tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    end_caption = time.time()
    
    print(f"\nPedestrian {ped_idx} sees: {generated_caption}")
    print(f"Caption time: {end_caption - start_caption:.2f}s")
    
    # Generate decision based on caption
    prompt = f"You are a pedestrian in a city. You see: '{generated_caption}'. What should you do next? Give a brief decision in one sentence."
    messages = [{"role": "user", "content": prompt}]
    text = llm_tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True
    )
    model_inputs = llm_tokenizer([text], return_tensors="pt").to(llm_model.device)
    
    start_llm = time.time()
    generated_ids = llm_model.generate(**model_inputs, max_new_tokens=128)
    output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()
    end_llm = time.time()
    
    # Parse thinking content
    try:
        index = len(output_ids) - output_ids[::-1].index(151668)  # </think>
    except ValueError:
        index = 0
    
    thinking_content = llm_tokenizer.decode(output_ids[:index], skip_special_tokens=True).strip("\n")
    decision = llm_tokenizer.decode(output_ids[index:], skip_special_tokens=True).strip("\n")
    
    if thinking_content:
        print(f"Thinking: {thinking_content[:100]}...")
    print(f"Decision: {decision}")
    print(f"LLM time: {end_llm - start_llm:.2f}s")
    
    return generated_caption, decision, img_rgb


# Spawn NPC vehicles
for i in range(20):
    vehicle_bp = random.choice(bp_lib.filter('vehicle'))
    npc = world.try_spawn_actor(vehicle_bp, random.choice(spawn_points))
    if npc:
        npc.set_autopilot(True)

world.tick()

edges = [[0,1], [1,3], [3,2], [2,0], [0,4], [4,5], [5,1], [5,7], [7,6], [6,4], [6,2], [7,3]]
ii = 0
current_pedestrian_idx = 0  # Index for cycling through pedestrians

print("\nStarting main loop...")

while True:
    # Retrieve and reshape the image
    world.tick()
    #image = image_queue.get()
    #semantic_image = semantic_queue.get()

    #img = np.reshape(np.copy(image.raw_data), (image.height, image.width, 4))
    #semantic_img = np.reshape(np.copy(semantic_image.raw_data), (semantic_image.height, semantic_image.width, 4))
    ii += 1
    
    # Process pedestrian vision every 100 frames (to avoid overwhelming the models)
    if ii % 100 == 0 and len(pedestrians) > 0:
        # Get image from current pedestrian
        try:
            ped_image = pedestrian_queues[current_pedestrian_idx].get(timeout=10.0)
            caption, decision, img_rgb = process_pedestrian_vision(current_pedestrian_idx, ped_image)
            # Store in history
            pedestrian_histories[current_pedestrian_idx]['observations'].append(caption)
            pedestrian_histories[current_pedestrian_idx]['decisions'].append(decision)
            # Move to next pedestrian
            current_pedestrian_idx = (current_pedestrian_idx + 1) % len(pedestrians)
            cv2.imwrite(f'ims/im_{ii}.jpg', np.ascontiguousarray(img_rgb[:, :, :3]))
        except queue.Empty:
            print(f"Warning: No image from pedestrian {current_pedestrian_idx}")
    
    # Get the camera matrix 
    #world_2_camera = np.array(camera.get_transform().get_inverse_matrix())
    
    # List to store all valid bounding boxes for YOLO format
    yolo_labels = []
    


    # Save image and labels periodically
    if ii % 300 == 0:
        # Print pedestrian histories summary
        for idx, history in enumerate(pedestrian_histories):
            if history['observations']:
                print(f"Pedestrian {idx} - {len(history['observations'])} observations recorded")
    

cv2.destroyAllWindows()
#camera.stop()
#camera2.stop()
for ped_camera in pedestrian_cameras:
    ped_camera.stop()
for pedestrian in pedestrians:
    pedestrian.destroy()
vehicle.destroy()

print("\nFinal Pedestrian Histories:")
for idx, history in enumerate(pedestrian_histories):
    print(f"\n=== Pedestrian {idx} ===")
    for i, (obs, dec) in enumerate(zip(history['observations'], history['decisions'])):
        print(f"  Observation {i+1}: {obs}")
        print(f"  Decision {i+1}: {dec}")
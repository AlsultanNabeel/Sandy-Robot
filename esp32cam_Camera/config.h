#ifndef SANDY_ESP32CAM_CONFIG_H
#define SANDY_ESP32CAM_CONFIG_H

// ===== AI Thinker ESP32-CAM pins =====
#ifndef PWDN_GPIO_NUM
  #define PWDN_GPIO_NUM 32
#endif
#ifndef RESET_GPIO_NUM
  #define RESET_GPIO_NUM -1
#endif
#ifndef XCLK_GPIO_NUM
  #define XCLK_GPIO_NUM 0
#endif
#ifndef SIOD_GPIO_NUM
  #define SIOD_GPIO_NUM 26
#endif
#ifndef SIOC_GPIO_NUM
  #define SIOC_GPIO_NUM 27
#endif
#ifndef Y9_GPIO_NUM
  #define Y9_GPIO_NUM 35
#endif
#ifndef Y8_GPIO_NUM
  #define Y8_GPIO_NUM 34
#endif
#ifndef Y7_GPIO_NUM
  #define Y7_GPIO_NUM 39
#endif
#ifndef Y6_GPIO_NUM
  #define Y6_GPIO_NUM 36
#endif
#ifndef Y5_GPIO_NUM
  #define Y5_GPIO_NUM 21
#endif
#ifndef Y4_GPIO_NUM
  #define Y4_GPIO_NUM 19
#endif
#ifndef Y3_GPIO_NUM
  #define Y3_GPIO_NUM 18
#endif
#ifndef Y2_GPIO_NUM
  #define Y2_GPIO_NUM 5
#endif
#ifndef VSYNC_GPIO_NUM
  #define VSYNC_GPIO_NUM 25
#endif
#ifndef HREF_GPIO_NUM
  #define HREF_GPIO_NUM 23
#endif
#ifndef PCLK_GPIO_NUM
  #define PCLK_GPIO_NUM 22
#endif

#ifndef CAMERA_HTTP_PORT
  #define CAMERA_HTTP_PORT 80
#endif

#ifndef CAMERA_SERIAL_BAUD
  #define CAMERA_SERIAL_BAUD 115200
#endif

#ifndef CAMERA_BOOT_DELAY_MS
  #define CAMERA_BOOT_DELAY_MS 500
#endif

#ifndef CAMERA_WIFI_POLL_DELAY_MS
  #define CAMERA_WIFI_POLL_DELAY_MS 500
#endif

#ifndef CAMERA_STATUS_PRINT_INTERVAL_MS
  #define CAMERA_STATUS_PRINT_INTERVAL_MS 15000
#endif

#ifndef CAMERA_REBOOT_RESPONSE_DELAY_MS
  #define CAMERA_REBOOT_RESPONSE_DELAY_MS 300
#endif

#ifndef CAMERA_XCLK_FREQ_HZ
  #define CAMERA_XCLK_FREQ_HZ 20000000
#endif

#ifndef CAMERA_DEBUG_LEVEL
  #define CAMERA_DEBUG_LEVEL 3
#endif

#ifndef CAMERA_USE_STATIC_IP
  #define CAMERA_USE_STATIC_IP true
#endif

#ifndef CAMERA_LOCAL_IP_1
  #define CAMERA_LOCAL_IP_1 192
  #define CAMERA_LOCAL_IP_2 168
  #define CAMERA_LOCAL_IP_3 1
  #define CAMERA_LOCAL_IP_4 150
#endif

#ifndef CAMERA_GATEWAY_1
  #define CAMERA_GATEWAY_1 192
  #define CAMERA_GATEWAY_2 168
  #define CAMERA_GATEWAY_3 1
  #define CAMERA_GATEWAY_4 1
#endif

#ifndef CAMERA_SUBNET_1
  #define CAMERA_SUBNET_1 255
  #define CAMERA_SUBNET_2 255
  #define CAMERA_SUBNET_3 255
  #define CAMERA_SUBNET_4 0
#endif

#ifndef CAMERA_PRIMARY_DNS_1
  #define CAMERA_PRIMARY_DNS_1 8
  #define CAMERA_PRIMARY_DNS_2 8
  #define CAMERA_PRIMARY_DNS_3 8
  #define CAMERA_PRIMARY_DNS_4 8
#endif

#ifndef CAMERA_SECONDARY_DNS_1
  #define CAMERA_SECONDARY_DNS_1 1
  #define CAMERA_SECONDARY_DNS_2 1
  #define CAMERA_SECONDARY_DNS_3 1
  #define CAMERA_SECONDARY_DNS_4 1
#endif

#ifndef CAMERA_DEFAULT_ENABLED
  #define CAMERA_DEFAULT_ENABLED false
#endif

#ifndef CAMERA_DEFAULT_FRAME_SIZE
  #define CAMERA_DEFAULT_FRAME_SIZE FRAMESIZE_VGA
#endif

#ifndef CAMERA_DEFAULT_JPEG_QUALITY
  #define CAMERA_DEFAULT_JPEG_QUALITY 12
#endif

#ifndef CAMERA_DEFAULT_FB_COUNT
  #define CAMERA_DEFAULT_FB_COUNT 2
#endif

#ifndef CAMERA_VERTICAL_FLIP
  #define CAMERA_VERTICAL_FLIP 1
#endif

#ifndef CAMERA_STREAM_FRAME_DELAY_MS
  #define CAMERA_STREAM_FRAME_DELAY_MS 80
#endif

#endif

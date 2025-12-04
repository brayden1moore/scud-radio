#include "DEV_Config.h"
#include "LCD_2inch.h"
#include "GUI_Paint.h"
#include "GUI_BMP.h"
#include <stdio.h>		
#include <stdlib.h>		

#define SPLASH_IMAGE_PATH "./pic/scud_splash_1_black.bmp"

void LCD_2IN_splash_display(void)
{
    /* Module Init (Initializes SPI and GPIO) */
    if(DEV_ModuleInit() != 0){
        printf("ERROR: Failed to initialize hardware module.\r\n");
        exit(1);
    }
	
    /* LCD Init */
    LCD_2IN_Init();
    LCD_2IN_Clear(WHITE);
    LCD_SetBacklight(1023); 
	
    // Calculate required memory for the image buffer (2 bytes per pixel)
    UDOUBLE Imagesize = LCD_2IN_HEIGHT * LCD_2IN_WIDTH * 2;
    UWORD *BlackImage;
    
    if((BlackImage = (UWORD *)malloc(Imagesize)) == NULL) {
        printf("ERROR: Failed to allocate memory for image buffer.\r\n");
        DEV_ModuleExit();
        exit(1);
    }
	
    Paint_NewImage(BlackImage, LCD_2IN_WIDTH, LCD_2IN_HEIGHT, 270, WHITE, 16);
    Paint_Clear(WHITE);
    Paint_SetRotate(ROTATE_270);
    
    // --- CORE SPLASH LOGIC ---
    
    printf("Loading splash image: %s\r\n", SPLASH_IMAGE_PATH);
    
    // 1. Read the BMP file into the BlackImage buffer
    if (GUI_ReadBmp(SPLASH_IMAGE_PATH) != 0) {
        printf("ERROR: Failed to read BMP file.\r\n");
        
        // As a fallback, draw a red box if the image fails to load
        Paint_DrawRectangle(10, 10, LCD_2IN_WIDTH-10, LCD_2IN_HEIGHT-10, RED, DOT_PIXEL_1X1, DRAW_FILL_FULL);
        
        LCD_2IN_Display((UBYTE *)BlackImage);
        
        // Wait briefly for the user to see the error, then exit
        DEV_Delay_ms(2000); 
    }
    
    // 2. Refresh the picture in RAM to LCD
    LCD_2IN_Display((UBYTE *)BlackImage);
    
    // --- CLEAN UP AND EXIT ---
    
    // Free the allocated memory
    free(BlackImage);
    BlackImage = NULL;
    
    // Exit the hardware module cleanly
    DEV_ModuleExit();
    
    // Exit successfully
    exit(0);
}

// You will need a main function that calls the splash function
int main(void)
{
    LCD_2IN_splash_display();
    return 0;
}

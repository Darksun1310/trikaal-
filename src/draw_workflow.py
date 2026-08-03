import matplotlib.pyplot as plt
import matplotlib.patches as patches

def draw_workflow():
    # Set up figure and axis
    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Color Palette (Modern, clean, high-contrast)
    bg_color = "#f8f9fa"
    box_color_1 = "#2b5c8f"  # Slate Blue (Data ingestion)
    box_color_2 = "#3a86c8"  # Ocean Blue (Processing)
    box_color_3 = "#e67e22"  # Amber (SSI)
    box_color_4 = "#8e44ad"  # Purple (ETAS)
    box_color_5 = "#16a085"  # Teal (PSHA)
    box_color_6 = "#2c3e50"  # Dark Slate (Bulletin)
    text_color_white = "#ffffff"
    arrow_color = "#7f8c8d"

    # Define helper for drawing boxes
    def draw_box(x, y, w, h, text, title, color):
        # Draw shadow
        shadow = patches.FancyBboxPatch((x+0.5, y-0.5), w, h, boxstyle="round,pad=0.3",
                                        facecolor="#cccccc", edgecolor="none", alpha=0.3)
        ax.add_patch(shadow)
        
        # Draw box
        box = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3",
                                     facecolor=color, edgecolor="none")
        ax.add_patch(box)
        
        # Draw Title
        ax.text(x + w/2, y + h * 0.75, title, color=text_color_white, fontsize=12,
                fontweight='bold', ha='center', va='center')
        # Draw text description
        ax.text(x + w/2, y + h * 0.35, text, color=text_color_white, fontsize=8.5,
                ha='center', va='center', wrap=True)

    # Box coordinates and content
    # Col 1: Ingestion & Preprocessing
    draw_box(5, 70, 24, 18, 
             "USGS ComCat & ISC\nMulti-source Harvesting", 
             "1. Catalog Ingestion", box_color_1)
             
    draw_box(5, 38, 24, 18, 
             "Haversine Spatiotemporal\nDeduplication & Mc=3.0", 
             "2. Deduplication", box_color_2)

    # Col 2: Analyses (SSI & ETAS)
    draw_box(38, 70, 24, 18, 
             "b-value, Event Rate,\n& Spatial Clustering", 
             "3. Stress Index (SSI)", box_color_3)

    draw_box(38, 38, 24, 18, 
             "Vectorized Likelihood &\nConditional Forecasting", 
             "4. Vectorized ETAS", box_color_4)

    # Col 3: Hazard & Operations
    draw_box(71, 70, 24, 18, 
             "PGA Exceedance Maps\nBedrock Hazard Curves", 
             "5. PSHA Engine", box_color_5)

    draw_box(71, 38, 24, 18, 
             "Real-time Alerting &\nHazard Amplification", 
             "6. Risk Bulletin", box_color_6)

    # Helper to draw arrows
    def draw_arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", lw=2, color=arrow_color,
                                    shrinkA=5, shrinkB=5))

    # Connect boxes with arrows
    # Ingestion -> Deduplication
    draw_arrow(17, 70, 17, 56)
    
    # Deduplication -> SSI
    draw_arrow(29, 47, 38, 79)
    
    # Deduplication -> ETAS
    draw_arrow(29, 47, 38, 47)
    
    # SSI -> PSHA
    draw_arrow(62, 79, 71, 79)
    
    # ETAS -> PSHA
    draw_arrow(62, 47, 71, 79)
    
    # ETAS -> Bulletin
    draw_arrow(62, 47, 71, 47)
    
    # PSHA -> Bulletin
    draw_arrow(83, 70, 83, 56)

    plt.tight_layout()
    plt.savefig("outputs/pipeline_workflow.png", bbox_inches='tight', facecolor='white', dpi=300)
    plt.close()

if __name__ == "__main__":
    draw_workflow()
    print("Workflow diagram generated successfully in outputs/pipeline_workflow.png")

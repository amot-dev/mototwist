---
next: false
---


# User Guide


## User Management

Twists may be viewed without an account, but creating a Twist requires one. If enabled by an admin, you can create your own account from the login modal.

  -  **Verification:**
      New accounts need to be verified if `EMAIL_ENABLED` is `True`. Most actions can only be performed by verified users.

  -  **Deactivation:**
      Accounts may be deactivated. Only an admin can reactivate it.

  -  **Deletion:**
      Accounts may be deleted. It will be gone forever, but Twists and rides will remain.

  -  **Promotion:**
      Only an admin can create or promote more admins. Initially, MotoTwist starts up with exactly one admin user.


## Drawing a New Twist

When you a creating a Twist, your map cursor will be a crosshair. Waypoints can be placed, dragged, named, and deleted.

  -  **Placing Waypoints:**
      Placing waypoints is as easy as clicking on the map in the desired location. Note that this should be on or close to a road. Waypoints not near roads will be snapped to a road in the final route.

  -  **Dragging Waypoints:**
      Clicking and holding a waypoint will allow you to move it around.

  -  **Naming Waypoints:**
      Clicking on a waypoint will allow naming it. The first and last waypoints must be named.

  -  **Shaping Points:**
      Waypoints other than the first and last are shaping points by default. These waypoints will be used to determine the Twist's final route, but will never be displayed. Use these as you would use dragging the route in Google Maps to achieve your desired route. You may name them to have them be displayed as part of the Twist.

  -  **Inserting Waypoints:**
      Waypoints may be inserted before the last waypoint by right-clicking. This is useful for adding shaping points to modify the path taken.

  -  **Deleting Waypoints:**
      Clicking on a waypoint will allow deleting it. Keep in mind that at least two waypoints are required to create a Twist.

  -  **Entering Twist Details:**
      Once your route is ready, additional details can be specified for the Twist, including the name and whether it is paved or unpaved.

<video autoplay loop muted playsinline style="width: 100%; border-radius: 8px;">
  <source src="/demo_new_twist.webm" type="video/webm">
</video>


> [!TIP]
> Twists should be predominantly paved or unpaved. If they're a combination of both, select whichever was "the main attraction" of the Twist, as each type has different criteria they're rated on. If both segments are fun, consider splitting the Twist!


## Riding Twists

From the sidebar, you can now ride your Twist! There's a number of different criteria you can rate your ride on, and hovering over each will give a brief description. You will also need to specify the weather conditions, which can be filtered for later.

![A screenshot of MotoTwist, featuring the ride modal open to submit a new ride](/screenshot_ride_modal.png)
![A screenshot of MotoTwist, featuring the ride list open, showing existing rides](/screenshot_ride_list.png)


## Searching/Filtering

Twists can be discovered and organized using several powerful filtering layers:

  - **Text Search**: Quickly find a Twist by name.

  - **Views**: Toggle between "Trending" (high recent activity) or "Hidden Gems" (high quality, but low ride volume).

  - **Surface Type**: Toggle between paved and unpaved (dirt/gravel) Twists.

  - **Authorship & Ride History**: Filter by Twists you created vs. others, or by those you have personally ridden vs. those you haven't.

  - **Weather Conditions**: Filter based on real-world conditions recorded during rides, such as temperature, light levels, or precipitation.

  - **Rating Ranges**: Use sliders to filter by overall average quality or drill down into specific criteria (like "Twistyness" or "Seclusion").

![A screenshot of MotoTwist, featuring the filter modal and its options](/screenshot_filter.png)


## Exporting

Twists can be exported, currently to either GPX Tracks or Routes. This can be useful for actually following them using a GPS!

  - Twists can be added to or removed from the export cart via the export button in the bottom right of the popup.

  - If there are items ready to export, the export cart icon will appear in the bottom right.

  - From the export cart, any number of Twists can be exported together in a collection.

![A screenshot of MotoTwist, featuring the export cart](/screenshot_export.png)


## General Use

  - Clicking on a Twist in the list will pan the map to that Twist and open its popup.

  - Clicking on a Twist on the map will open its popup, revealing more information about it.

  - Twists can be hidden.

  - Clicking on a Waypoints on the map will show its name.

  - Twists can be modified or deleted.

  - Rides can be deleted, but not modified.

![A screenshot of MotoTwist, featuring a popup open for a Twist with no rides](/screenshot_no_rides.png)

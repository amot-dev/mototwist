# Custom Criteria

Criteria used by MotoTwist is all defined in `/config/criteria.json` in the container (it's baked into the image). The default criteria were picked by me, for me. They may be useful for some people, but not everyone.


## Changing Criteria

Custom criteria should be placed in a `criteria.json` file in the same directory as your `docker-compose.yml` file.

<<< @/../criteria.json


### Fields

  -  **`slug`:**
    This is the internal representation of the criterion name and must use underscores instead of spaces. This is automatically converted to title case with spaces for display.

      For example: `surface_consistency` becomes **Surface Consistency**.

  -  **`description`:**
    This is the description of the criterion, to be displayed to the user in MotoTwist itself.

  -  **`for_paved`/`for_unpaved`:**
    Determines if the criterion applies to paved Twists, unpaved Twists, or both. Technically, neither is also possible, but the only effect this has is wasting precious storage space for no reason.


## Criteria Mount

Finally, add the following to the `mototwist` service in the `docker-compose.yml` file to mount your custom criteria.

``` yml
volumes:
    - ./criteria.json:/config/criteria.json:ro
```

> [!WARNING]
> Changes to `criteria.json` only take effect on the first start. Once the database is initialized, this file is ignored. There is no way to change criteria post-initialization.

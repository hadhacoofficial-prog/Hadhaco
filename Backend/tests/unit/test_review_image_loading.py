"""Regression test: POST /api/v1/reviews with photos returned 500.

ReviewOut builds each photo from ``image.variants``. Review.images is
selectin-loaded, but Image.variants was lazy="select", so serializing the
review after commit triggered a lazy load outside the async greenlet:

    sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called

The review and photo were already committed, so the same lazy load also
broke every later read of that product's reviews. Both relationships must
load eagerly so a Review is fully serializable once its query returns.
"""

from sqlalchemy import inspect

from app.core.model_registry import import_all_models
from app.modules.media.models import Image
from app.modules.reviews.models import Review


def test_review_images_and_their_variants_load_eagerly() -> None:
    import_all_models()
    assert inspect(Review).relationships["images"].lazy == "selectin"
    assert inspect(Image).relationships["variants"].lazy == "selectin"

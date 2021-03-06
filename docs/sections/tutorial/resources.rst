Parametrizing pipelines with resources
--------------------------------------

.. toctree::
  :maxdepth: 1
  :hidden:

Often, we'll want to be able to configure pipeline-wide facilities, like uniform access to the
file system, databases, or cloud services. Dagster models interactions with features of the external
environment like these as resources (and library modules such as ``dagster_aws``, ``dagster_gcp``,
and even ``dagster_slack`` provide out-of-the-box implementations for many common external
services).

Typically, your data processing pipelines will want to store their results in a data warehouse
somewhere separate from the raw data sources. We'll adjust our toy pipeline so that it does a little
more work on our cereal dataset, stores the finished product in a swappable data warehouse, and
lets the team know when we're finished.

You might have noticed that our cereal dataset isn't normalized -- that is, the serving sizes for
some cereals are as small as a quarter of a cup, and for others are as large as a cup and a half.
This grossly understates the nutritional difference between our different cereals.

Let's transform our dataset and then store it in a normalized table in the warehouse:

.. literalinclude:: ../../../examples/dagster_examples/intro_tutorial/resources.py
    :caption: resources.py
    :linenos:
    :lineno-start: 57
    :lines: 57-80
    :emphasize-lines: 24
    :language: python

Resources are another facility that Dagster makes available on the ``context`` object passed to
solid logic. Note that we've completely encapsulated access to the database behind the call to
``context.resources.warehouse.update_normalized_cereals``. This means that we can easily swap resource
implementations -- for instance, to test against a local SQLite database instead of a production
Snowflake database; to abstract software changes, such as swapping raw SQL for SQLAlchemy; or to
accomodate changes in business logic, like moving from an overwriting scheme to append-only,
date-partitioned tables.

To implement a resource and specify its config schema, we use the
:py:class:`@resource <dagster.resource>` decorator. The decorated function should return whatever
object you wish to make available under the specific resource's slot in ``context.resources``.
Resource constructor functions have access to their own ``context`` argument, which gives access to
resource-specific config. (Unlike the contexts we've seen so far, which are instances of
:py:class:`SystemComputeExecutionContext <dagster.SystemComputeExecutionContext>`, this context is
an instance of :py:class:`InitResourceContext <dagster.InitResourceContext>`.)

.. literalinclude:: ../../../examples/dagster_examples/intro_tutorial/resources.py
    :caption: resources.py
    :linenos:
    :lineno-start: 16
    :lines: 16-45
    :emphasize-lines: 28-30
    :language: python

The last thing we need to do is to attach the resource to our pipeline, so that it's properly
initialized when the pipeline run begins and made available to our solid logic as
``context.resources.warehouse``.

.. literalinclude:: ../../../examples/dagster_examples/intro_tutorial/resources.py
    :caption: resources.py
    :linenos:
    :lineno-start: 83
    :lines: 83-91
    :emphasize-lines: 2-6
    :language: python

All resources are associated with a :py:class:`ModeDefinition <dagster.ModeDefinition>`. So far,
all of our pipelines have had only a single, system default mode, so we haven't had to tell Dagster
what mode to run them in. Even in this case, where we provide a single anonymous mode to the
:py:func:`@pipeline <dagster.pipeline>` decorator, we won't have to specify which mode to use (it
will take the place of the ``default`` mode).

We can put it all together with the following config:

.. literalinclude:: ../../../examples/dagster_examples/intro_tutorial/resources.yaml
    :caption: resources.yaml
    :language: YAML
    :linenos:
    :emphasize-lines: 1-4

(Here, we pass the special string ``":memory:"`` in config as the connection string for our
database -- this is how SQLite designates an in-memory database.)


Expressing resource dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We've provided a ``warehouse`` resource to our pipeline, but we're still manually managing our
pipeline's dependency on this resource. Dagster also provides a way for solids to advertise
their resource requirements, to make it easier to keep track of which resources need to be
provided for a pipeline.

.. literalinclude:: ../../../examples/dagster_examples/intro_tutorial/required_resources.py
    :caption: required_resources.py
    :linenos:
    :lineno-start: 55
    :lines: 55-78
    :emphasize-lines: 1
    :language: python

Now, the Dagster machinery knows that this solid requires a resource called ``warehouse`` to be
present on its mode definitions, and will complain if that resource is not present.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math

import numpy as np
import tensorflow as tf

from datasets import dataset_factory
from nets import nets_factory
from preprocessing import preprocessing_factory

slim = tf.contrib.slim

tf.app.flags.DEFINE_integer(
    'batch_size', 4, 'The number of samples in each batch.')

tf.app.flags.DEFINE_string(
    'checkpoint_path', None,
    'The directory where the model was written to or an absolute path to a '
    'checkpoint file.')

tf.app.flags.DEFINE_string(
    'eval_dir', 'train/eval', 'Directory where the results are saved to.')

tf.app.flags.DEFINE_integer(
    'num_preprocessing_threads', 4,
    'The number of threads used to create the batches.')

tf.app.flags.DEFINE_string(
    'dataset_name', None, 'The name of the dataset to load.')

tf.app.flags.DEFINE_string(
    'dataset_split_name', 'validation', 'The name of the train/test split.')

tf.app.flags.DEFINE_string(
    'dataset_dir', None, 'The directory where the dataset files are stored.')

tf.app.flags.DEFINE_string(
    'dataset_type', 'rgb', 'The type of images in the dataset (RGB/RGBD)')

tf.app.flags.DEFINE_string(
    'model_name', None, 'The name of the architecture to evaluate.')

tf.app.flags.DEFINE_string(
    'preprocessing_name', None, 'The name of the preprocessing to use. If left '
    'as `None`, then the model_name flag is used.')


tf.app.flags.DEFINE_integer(
    'crop_larger_dim', 220, 'Higher dimension of preprocessing Crop size for input image ')

tf.app.flags.DEFINE_integer(
    'crop_smaller_dim', 220, 'Smaller dimension of preprocessing crop size for input image')

tf.app.flags.DEFINE_integer(
    'eval_image_size', 473, 'Eval image size')

tf.app.flags.DEFINE_integer(
    'num_classes', None, 'Number of classes in dataset')

tf.app.flags.DEFINE_integer(
    'training_size', None, 'Number of training images in the dataset')

tf.app.flags.DEFINE_integer(
    'validation_size', None, 'Number of validation images in the dataset')

tf.app.flags.DEFINE_string(
    'classes', None,
    'The classes to classify.')

FLAGS = tf.app.flags.FLAGS


def main(_):
  if not FLAGS.dataset_dir:
    raise ValueError('You must supply the dataset directory with --dataset_dir')
  dataset_type=FLAGS.dataset_type
  tf.logging.set_verbosity(tf.logging.INFO)
  with tf.Graph().as_default():
    tf_global_step = slim.get_or_create_global_step()

    ######################
    # Select the dataset #
    ######################
    dataset = dataset_factory.get_dataset(
        FLAGS.dataset_type, FLAGS.dataset_split_name, FLAGS.training_size, FLAGS.validation_size, FLAGS.num_classes, FLAGS.dataset_dir)

    num_classes = dataset.num_classes

    ####################
    # Select the model #
    ####################
    network_fn = nets_factory.get_network_fn(
        FLAGS.model_name,
        num_classes=num_classes,
        is_training=False)

    ##############################################################
    # Create a dataset provider that loads data from the dataset #
    ##############################################################
    provider = slim.dataset_data_provider.DatasetDataProvider(
        dataset,
        shuffle=False,
        common_queue_capacity=2 * FLAGS.batch_size,
        common_queue_min=FLAGS.batch_size)

    if (dataset_type=='rgb'):
        [image, label] = provider.get(['image', 'label'])

        preprocessing_name = FLAGS.preprocessing_name or FLAGS.model_name
        image_preprocessing_fn = preprocessing_factory.get_preprocessing(
            preprocessing_name,
            is_training=False)

        eval_image_size = FLAGS.eval_image_size or network_fn.default_image_size

        image, label = image_preprocessing_fn(image, eval_image_size, eval_image_size,
                                              label=label, resize_side_max=FLAGS.crop_larger_dim, resize_side_min=FLAGS.crop_smaller_dim)

        images, labels = tf.train.batch(
            [image, label],
            batch_size=FLAGS.batch_size,
            num_threads=FLAGS.num_preprocessing_threads,
            capacity=5 * FLAGS.batch_size)


        logits, _ = network_fn(images)
    elif (dataset_type=='rgbd'):
        [image, label, depth] = provider.get(['image', 'label', 'depth'])

        preprocessing_name = FLAGS.preprocessing_name or FLAGS.model_name
        image_preprocessing_fn = preprocessing_factory.get_preprocessing(
            preprocessing_name,
            is_training=False)

        eval_image_size = FLAGS.eval_image_size or network_fn.default_image_size

        image, label, depth = image_preprocessing_fn(image, eval_image_size, eval_image_size,
                                              label=label, depth=depth,resize_side_max=FLAGS.crop_larger_dim, resize_side_min=FLAGS.crop_smaller_dim)

        images, labels, depths = tf.train.batch(
            [image, label, depth],
            batch_size=FLAGS.batch_size,
            num_threads=FLAGS.num_preprocessing_threads,
            capacity=5 * FLAGS.batch_size)

        ####################
        # Define the model #
        ####################
        logits, _ = network_fn(images, depths)
    variables_to_restore = slim.get_variables_to_restore()
    predictions = tf.argmax(logits, 3)
    labels = tf.squeeze(labels)
    predictions = tf.squeeze(predictions)
    #mask=tf.cast(tf.not_equal(labels,0),tf.int32)
    mask=tf.cast(tf.less_equal(labels,num_classes-1),tf.int32)
    #print(mask.get_shape())
    print("NUM_CLASSES: "+str(num_classes))
    # Define the metrics:
    names_to_values, names_to_updates = slim.metrics.aggregate_metric_map({
        'Pixel ACC': slim.metrics.streaming_accuracy(predictions, labels,weights=mask),
        'IOU': slim.metrics.streaming_mean_iou(predictions, labels, num_classes,weights=mask),
    })

    # Print the summaries to screen.
    for name, value in names_to_values.iteritems():
      summary_name = 'eval/%s' % name
      op = tf.scalar_summary(summary_name, value, collections=[])
      op = tf.Print(op, [value], summary_name)
      tf.add_to_collection(tf.GraphKeys.SUMMARIES, op)

    num_batches = math.ceil(dataset.num_samples / float(FLAGS.batch_size))

    #if tf.gfile.IsDirectory(FLAGS.checkpoint_path):
    checkpoint_path = tf.train.latest_checkpoint(FLAGS.checkpoint_path)
    #else:
    #  checkpoint_path = FLAGS.checkpoint_path

    tf.logging.info('Evaluating %s' % checkpoint_path)

    slim.evaluation.evaluate_once(
        master='',
        checkpoint_path=checkpoint_path,
        logdir=FLAGS.eval_dir,
        num_evals=num_batches,
        eval_op=names_to_updates.values(),
        variables_to_restore=variables_to_restore)


if __name__ == '__main__':
  tf.app.run()

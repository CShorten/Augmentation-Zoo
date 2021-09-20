import keras
import numpy as np
from tensorflow.keras import layers
import tensorflow as tf

from tensorflow.keras.applications import ResNet152V2, ResNet50

def standard_model(x_train, input_shape=(32,32,3)):
  normalization_layer = keras.Sequential(
    [
      layers.experimental.preprocessing.Normalization(),
    ],
    name="normalization",
  )
  normalization_layer.layers[0].adapt(x_train)
  inputs = layers.Input(shape=input_shape)
  normalized = normalization_layer(inputs)
  resnet_outputs = ResNet152V2(include_top=False, weights=None)(normalized)
  flattened = layers.Flatten()(resnet_outputs)
  dense_1 = layers.Dense(512, activation="relu")(flattened)
  dense_2 = layers.Dense(512, activation="relu")(dense_1)
  outputs = layers.Dense(10, activation="softmax")(dense_2)
  model = keras.Model(inputs=inputs, outputs=outputs)
  return model

def ResNet50_with_upsampling(x_train, input_shape=(32,32,3)):
  normalization_layer = keras.Sequential(
    [
      layers.experimental.preprocessing.Normalization(),
      layers.experimental.preprocessing.Resizing(72, 72),
    ],
    name = "no_data_augmentation",
  )
  normalization_layer.layers[0].adapt(x_train)
  inputs = layers.Input(shape=input_shape)
  normalized = normalization_layer(inputs)
  resnet_outputs = ResNet50(weights=None, include_top=False, input_shape=(72,72,3))
  flattened = layers.Flatten()(resnet_outputs)
  dense_1 = layers.Dense(512, activation="relu")(flattened)
  dense_2 = layers.Dense(512, activation="relu")(dense_1)
  outputs = layers.Dense(10, activation="softmax")(dense_2)
  model = keras.Model(inputs=inputs, outputs=outputs)
  return model

def compile_model(model, lr=0.001):
  model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
    loss = keras.losses.CategoricalCrossentropy(from_logits=False),
    metrics = [
      keras.metrics.CategoricalAccuracy(name="accuracy"),
    ],
  )

# Vision Transformer
# implementation from Khalid Salama, cite: https://keras.io/examples/vision/image_classification_with_vision_transformer/
def create_vit_classifier(x_train):
  import tensorflow_addons as tfa            
  patch_size = 6  # Size of the patches to be extract from the input images
  num_patches = (image_size // patch_size) ** 2
  projection_dim = 64
  num_heads = 4
  transformer_units = [
      projection_dim * 2,
      projection_dim,
  ]  # Size of the transformer layers
  transformer_layers = 8
  mlp_head_units = [2048, 1024]  # Size of the dense layers of the final classifier
  
  def mlp(x, hidden_units, dropout_rate):
    for units in hidden_units:
        x = layers.Dense(units, activation=tf.nn.gelu)(x)
        x = layers.Dropout(dropout_rate)(x)
    return x

  class Patches(layers.Layer):
    def __init__(self, patch_size):
        super(Patches, self).__init__()
        self.patch_size = patch_size

    def call(self, images):
        batch_size = tf.shape(images)[0]
        patches = tf.image.extract_patches(
            images=images,
            sizes=[1, self.patch_size, self.patch_size, 1],
            strides=[1, self.patch_size, self.patch_size, 1],
            rates=[1, 1, 1, 1],
            padding="VALID",
        )
        patch_dims = patches.shape[-1]
        patches = tf.reshape(patches, [batch_size, -1, patch_dims])
        return patches     
                   
  class PatchEncoder(layers.Layer):
    def __init__(self, num_patches, projection_dim):
          super(PatchEncoder, self).__init__()
          self.num_patches = num_patches
          self.projection = layers.Dense(units=projection_dim)
          self.position_embedding = layers.Embedding(
              input_dim=num_patches, output_dim=projection_dim
          )

    def call(self, patch):
          positions = tf.range(start=0, limit=self.num_patches, delta=1)
          encoded = self.projection(patch) + self.position_embedding(positions)
          return encoded
     
  inputs = layers.Input(shape=input_shape)
                   
  data_augmentation = keras.Sequential(
    [
        layers.Normalization(),
        layers.Resizing(image_size, image_size),
    ],
    name="data_augmentation",
  )
  # Compute the mean and the variance of the training data for normalization.
  data_augmentation.layers[0].adapt(x_train)
                   
  # Augment data.
  augmented = data_augmentation(inputs)
  # Create patches.
  patches = Patches(patch_size)(augmented)
  # Encode patches.
  encoded_patches = PatchEncoder(num_patches, projection_dim)(patches)

  # Create multiple layers of the Transformer block.
  for _ in range(transformer_layers):
      # Layer normalization 1.
      x1 = layers.LayerNormalization(epsilon=1e-6)(encoded_patches)
      # Create a multi-head attention layer.
      attention_output = layers.MultiHeadAttention(
            num_heads=num_heads, key_dim=projection_dim, dropout=0.1
      )(x1, x1)
      # Skip connection 1.
      x2 = layers.Add()([attention_output, encoded_patches])
      # Layer normalization 2.
      x3 = layers.LayerNormalization(epsilon=1e-6)(x2)
      # MLP.
      x3 = mlp(x3, hidden_units=transformer_units, dropout_rate=0.1)
      # Skip connection 2.
      encoded_patches = layers.Add()([x3, x2])

  # Create a [batch_size, projection_dim] tensor.
  representation = layers.LayerNormalization(epsilon=1e-6)(encoded_patches)
  representation = layers.Flatten()(representation)
  representation = layers.Dropout(0.5)(representation)
  # Add MLP.
  features = mlp(representation, hidden_units=mlp_head_units, dropout_rate=0.5)
  # Classify outputs.
  logits = layers.Dense(10)(features)
  # Create the Keras model.
  model = keras.Model(inputs=inputs, outputs=logits)
  return model

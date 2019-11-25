# -*- coding: utf-8 -*-
"""
Created on: 2019/5/27 14:29
@Author: zsfeng
"""

import tensorflow as tf


def neural_tensor_layer(class_vector, query_encoder, out_size=100):
    """neural tensor layer (NTN)"""
    C, H = class_vector.shape
    # print("class_vector shape:", class_vector.shape)
    # print("query_encoder shape:", query_encoder.shape)
    M = tf.get_variable("M", [H, H, out_size], dtype=tf.float32,
                        initializer=tf.keras.initializers.glorot_normal())
    mid_pro = []
    for slice in range(out_size):
        slice_inter = tf.matmul(tf.matmul(class_vector, M[:, :, slice]), query_encoder, transpose_b=True)  # (C,Q)
        mid_pro.append(slice_inter)
    tensor_bi_product = tf.concat(mid_pro, axis=0)  # (C*K,Q)
    # print("tensor_bi_product shape:{}".format(tensor_bi_product.shape))
    V = tf.nn.relu(tf.transpose(tensor_bi_product))
    W = tf.get_variable("w", [C * out_size, C], dtype=tf.float32,
                        initializer=tf.keras.initializers.glorot_normal())
    b = tf.get_variable("b", [C], dtype=tf.float32,
                        initializer=tf.keras.initializers.glorot_normal())
    # probs:[k_query, c]
    probs = tf.nn.sigmoid(tf.matmul(V, W) + b)  # (Q,C)
    return probs


def self_attention(inputs):
    # inputs: [batch=(k_support+k_query)], seq_length, hidden_size]
    _, sequence_length, hidden_size = inputs.shape
    with tf.variable_scope('self_attn'):
        # inputs:[batch, seq_length, hidden_size]
        # x_proj:[batch, seq_length, hidden_size]
        x_proj = tf.layers.Dense(units=hidden_size)(inputs) # W_a1:[hidden_size, hidden_size],应该是最后一维上相乘
        print("x_proj shape:", x_proj.shape) # [?, 40, 40]
        x_proj = tf.nn.tanh(x_proj)
        # u_w:[hidden_size, 1]
        u_w = tf.get_variable('W_a2',
                              shape=[hidden_size, 1],
                              dtype=tf.float32,
                              initializer=tf.keras.initializers.glorot_normal())
        # x_proj:[batch, seq_length, hidden_size]
        # u_w:[hidden_size, 1]
        # x:[batch, seq_length, 1]
        x = tf.tensordot(a=x_proj, b=u_w, axes=1) # tensordot:在x_proj的倒数第axes=1维上以及u_w的第axes=1维上矩阵乘积
        print("x shape:", x.shape) # [?, 37, 1]
        # alphas:[batch, seq_length, 1]
        alphas = tf.nn.softmax(x, axis=1) # 在各时间步上计算softmax
        print("alphas shape", alphas.shape)
        # inputs_trans: [batch, hidden_size, seq_length]
        inputs_trans = tf.transpose(a=inputs, perm=[0, 2, 1])
        # inputs_trans: [batch, hidden_size, seq_length],batch中各时间步的向量
        # alphas:[batch, seq_length, 1], 各时间步的系数
        # output:[batch, hidden_size, 1], 各时间步加求和后的向量
        output = tf.matmul(inputs_trans, alphas) # 类似于batch_matmul
        # output:[batch, hidden_size]
        output = tf.squeeze(output, axis=-1)
        # output:[batch, hidden_size]
        return output


def dynamic_routing(input, b_IJ, iter_routing=3):
    ''' The routing algorithm.'''

    C, K, H = input.shape
    W = tf.get_variable('W_s', shape=[H, H],
                        dtype=tf.float32, initializer=tf.keras.initializers.glorot_normal())

    for r_iter in range(iter_routing):
        with tf.variable_scope('iter_' + str(r_iter)):
            d_I = tf.nn.softmax(tf.reshape(b_IJ, [C, K, 1]), axis=1)
            # for all samples j = 1, ..., K in class i:
            e_IJ = tf.reshape(tf.matmul(tf.reshape(input, [-1, H]), W), [C, K, -1])  # (C,K,H)
            c_I = tf.reduce_sum(tf.multiply(d_I, e_IJ), axis=1, keepdims=True)  # (C,1,H)
            c_I = tf.reshape(c_I, [C, -1])  # (C,H)
            c_I = squash(c_I)  # (C,H)
            c_produce_e = tf.matmul(e_IJ, tf.reshape(c_I, [C, H, 1]))  # (C,K,1)
            # for all samples j = 1, ..., K in class i:
            b_IJ += tf.reshape(c_produce_e, [C, K])

    return c_I


def squash(vector):
    '''Squashing function corresponding to Eq. 1'''
    vec_squared_norm = tf.reduce_sum(tf.square(vector), 1, keepdims=True)
    scalar_factor = vec_squared_norm / (1 + vec_squared_norm) / tf.sqrt(vec_squared_norm + 1e-9)
    vec_squashed = scalar_factor * vector  # element-wise
    return (vec_squashed)


if __name__ == "__main__":
    import numpy as np

    inputs = np.random.random((24, 5, 10))  # (3*3+3*5,seq_len,lstm_hidden_size*2)
    # print (inputs)
    inputs = tf.constant(inputs, dtype=tf.float32)
    encoder = self_attention(inputs)  # (k*c,lstm_hidden_size*2)

    support_encoder = tf.slice(encoder, [0, 0], [9, 10])
    query_encoder = tf.slice(encoder, [9, 0], [15, 10])

    support_encoder = tf.reshape(support_encoder, [3, 3, -1])
    b_IJ = tf.constant(
        np.zeros([3, 3], dtype=np.float32))
    class_vector = dynamic_routing(support_encoder, b_IJ)
    inter = neural_tensor_layer(class_vector, query_encoder, out_size=10)

    # test accuracy
    query_label = [0, 1, 2] * 5
    print(query_label)
    predict = tf.argmax(name="predictions", input=inter, axis=1)
    correct_prediction = tf.equal(tf.cast(predict, tf.int32), query_label)
    accuracy = tf.reduce_mean(name="accuracy", input_tensor=tf.cast(correct_prediction, tf.float32))
    labels_one_hot = tf.one_hot(query_label, 3, dtype=tf.float32)

    sess = tf.Session()
    with sess.as_default():
        sess.run(tf.global_variables_initializer())
        print(encoder.eval())
        print(query_encoder.eval())
        print(inter.eval())
        print(predict.eval())
        print(correct_prediction.eval())
        print(accuracy.eval())
